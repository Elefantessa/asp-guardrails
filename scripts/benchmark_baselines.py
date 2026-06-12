"""
Baseline comparison for the Cloudway thesis evaluation (RQ1, RQ2).

Runs 3 baselines on tests/fixtures/test_cases.json:

  Baseline A — LLM only:    No RAG, no ASP. Bare LLM call.
  Baseline B — RAG only:    RAG + LLM. No ASP validation.
  Baseline C — RAG + ASP:   Full pipeline (our system).

Outputs:
  logs/baseline_A_<timestamp>.json
  logs/baseline_B_<timestamp>.json
  logs/baseline_C_<timestamp>.json

Run:
    python scripts/benchmark_baselines.py [--baseline A|B|C|all]
"""

import argparse, json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_aws import ChatBedrock, BedrockEmbeddings
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.state import GuardrailsState
from src.agents.classifier import classifier_node
from src.agents.fact_extractor import fact_extraction_agent_node
from src.agents.asp_validator import asp_validator_node
from src.agents.decision import decision_node
from src.graph import build_graph
from src.telemetry import TRACER
from src.persistence.audit_log import log_turn
import src.agents.rag_agent as _ra
import src.agents.fact_extractor as _fe
from src.agents.rag_agent import rag_agent_node

# ── CRITICAL: clear stale env var credentials AFTER all imports ───────────────
# Each agent module calls load_dotenv() at import time which re-sets expired
# credentials from .env into os.environ, overriding ~/.aws/credentials.
# Popping after all imports ensures boto3 uses the fresh profile credentials.
for _k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
    os.environ.pop(_k, None)

# Reset agent LLM singletons so next call creates a fresh boto3 client
_ra._llm = None
_ra._retriever = None
_fe._llm = None


# ── Early credential validation ───────────────────────────────────────────────
def _check_aws_credentials() -> None:
    """Fail fast with a clear message if AWS credentials are expired or missing."""
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    try:
        profile = os.getenv("AWS_PROFILE", "default")
        session = boto3.Session(profile_name=profile)
        session.client("sts", region_name=os.getenv("AWS_DEFAULT_REGION", "eu-central-1")) \
              .get_caller_identity()
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("ExpiredTokenException", "ExpiredToken"):
            print("\n❌  AWS credentials expired.")
            print("    Update AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN in .env")
            print("    or run:  aws sso login --profile default\n")
        else:
            print(f"\n❌  AWS error ({code}): {e}\n")
        sys.exit(1)
    except NoCredentialsError:
        print("\n❌  No AWS credentials found. Check ~/.aws/credentials or .env\n")
        sys.exit(1)

_check_aws_credentials()

FIXTURE_PATH = Path("tests/fixtures/test_cases.json")
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# ── Shared LLM (fresh client each benchmark run) ─────────────────────────────

def _get_llm():
    """Always creates a fresh client so refreshed ~/.aws/credentials are used."""
    profile = os.getenv("AWS_PROFILE", "default")
    return ChatBedrock(
        model_id=os.getenv("BEDROCK_LLM", "eu.anthropic.claude-sonnet-4-6"),
        region_name=os.getenv("AWS_DEFAULT_REGION", "eu-central-1"),
        credentials_profile_name=profile,
        model_kwargs={"temperature": 0, "max_tokens": 1000},
    )


# ── Baseline A: LLM Only ──────────────────────────────────────────────────────

_LLMONLY_SYSTEM = (
    "You are a holiday booking assistant. Answer customer questions "
    "about TUI holiday packages policy accurately and concisely. "
    "If you do not know, say you do not know."
)

def run_llm_only(turns: list[str]) -> dict:
    """No RAG, no ASP. One LLM call with the full conversation history."""
    llm = _get_llm()
    messages = [SystemMessage(content=_LLMONLY_SYSTEM)]
    last_answer = ""
    t0 = time.time()
    for turn in turns:
        messages.append(HumanMessage(content=turn))
        resp = llm.invoke(messages)
        messages.append(resp)
        last_answer = resp.content
    latency_ms = int((time.time() - t0) * 1000)

    # Baseline A has no decision logic — it always "approves" (no rejection mechanism)
    # REFUSAL detection: heuristic only
    lower = last_answer.lower()
    if any(kw in lower for kw in ["not covered", "don't have information", "cannot help", "out of scope"]):
        decision = "refused_out_of_scope"
    elif "?" in last_answer and len(last_answer) < 200:
        decision = "pending_info"
    else:
        decision = "approved"

    return {"answer": last_answer, "decision": decision, "latency_ms": latency_ms}


# ── Baseline B: RAG Only graph ────────────────────────────────────────────────

def _build_rag_only_graph():
    """
    Modified graph: rag_agent → classifier → decision.
    Fact extractor and ASP validator are bypassed — decisions are based
    on CLAIM/REFUSAL markers only, never on ASP verification.
    Hallucinations cannot be detected.
    """

    def rag_only_decision(state: GuardrailsState) -> dict:
        if state.get("classification_error", False):
            return {"decision": "escalated"}
        if state.get("is_clarification", False):
            return {"decision": "pending_info"}
        if state.get("is_refusal", False):
            return {"decision": "refused_out_of_scope"}
        # Has CLAIM: lines → approved without ASP check
        return {"decision": "approved"}

    workflow = StateGraph(GuardrailsState)
    workflow.add_node("rag_agent", rag_agent_node)
    workflow.add_node("classifier", classifier_node)
    workflow.add_node("rag_only_router", rag_only_decision)
    workflow.add_edge(START, "rag_agent")
    workflow.add_edge("rag_agent", "classifier")
    workflow.add_edge("classifier", "rag_only_router")
    workflow.add_edge("rag_only_router", END)
    return workflow.compile(checkpointer=MemorySaver())


_rag_only_graph = None

def run_rag_only(turns: list[str], thread_id: str) -> dict:
    global _rag_only_graph
    if _rag_only_graph is None:
        _rag_only_graph = _build_rag_only_graph()

    config = {"configurable": {"thread_id": thread_id}}
    result = None
    t0 = time.time()
    for turn in turns:
        result = _rag_only_graph.invoke(
            {"messages": [HumanMessage(content=turn)]}, config=config
        )
    latency_ms = int((time.time() - t0) * 1000)
    ai = [m for m in result["messages"] if hasattr(m, "type") and m.type == "ai"]
    return {
        "answer": ai[-1].content if ai else "",
        "decision": result.get("decision", "error"),
        "latency_ms": latency_ms,
    }


# ── Baseline C: Full RAG + ASP (our system) ───────────────────────────────────

_full_graph = None

def run_full_pipeline(turns: list[str], thread_id: str) -> dict:
    global _full_graph
    if _full_graph is None:
        _full_graph = build_graph()

    config = {"configurable": {"thread_id": thread_id}}
    result = None
    t0 = time.time()
    for turn in turns:
        with TRACER.start_as_current_span("benchmark.graph.run") as span:
            span.set_attribute("baseline", "C")
            span.set_attribute("thread_id", thread_id)
            result = _full_graph.invoke(
                {"messages": [HumanMessage(content=turn)]}, config=config
            )
    latency_ms = int((time.time() - t0) * 1000)
    ai = [m for m in result["messages"] if hasattr(m, "type") and m.type == "ai"]
    answer = ai[-1].content if ai else ""
    out = {
        "answer": answer,
        "decision": result.get("decision", "error"),
        "violations": result.get("violations", []),
        "extracted_facts": result.get("extracted_facts", []),
        "retrieved_docs": result.get("retrieved_docs", []),
        "latency_ms": latency_ms,
    }
    log_turn(
        thread_id=thread_id,
        user_query=turns[-1],
        llm_answer=answer,
        extracted_facts=out["extracted_facts"],
        violations=out["violations"],
        decision=out["decision"],
        latency_ms=latency_ms,
        retrieved_docs=out["retrieved_docs"],
    )
    return out


# ── ASP direct evaluation (for hallucination cases) ───────────────────────────

def run_asp_direct(mock_facts: list[str], baseline: str) -> dict:
    """
    Inject pre-fabricated ASP facts directly into the validator.
    Baselines A and B cannot detect violations (no ASP) → always pass.
    Baseline C runs the real Clingo validator.
    """
    if baseline in ("A", "B"):
        return {
            "validation_passed": True,
            "violations": [],
            "decision": "approved",
            "latency_ms": 0,
        }

    # Baseline C: real ASP
    t0 = time.time()
    mock_state: GuardrailsState = {
        "messages": [],
        "retrieved_docs": [],
        "llm_answer": "",
        "is_clarification": False,
        "is_refusal": False,
        "classification_error": False,
        "extracted_claims": [],
        "extracted_facts": mock_facts,
        "validation_passed": False,
        "violations": [],
        "derived_facts": [],
        "decision": "error",
    }
    asp_result = asp_validator_node(mock_state)
    latency_ms = int((time.time() - t0) * 1000)
    decision = "escalated" if not asp_result["validation_passed"] else "approved"
    return {
        "validation_passed": asp_result["validation_passed"],
        "violations": asp_result["violations"],
        "decision": decision,
        "latency_ms": latency_ms,
    }


# ── Runner ────────────────────────────────────────────────────────────────────

def run_baseline(baseline: str, cases: list[dict]) -> list[dict]:
    label = {"A": "LLM Only", "B": "RAG Only", "C": "RAG + ASP (Cloudway)"}[baseline]
    print(f"\n{'='*60}")
    print(f"  Baseline {baseline}: {label}")
    print(f"{'='*60}")

    results = []
    for tc in cases:
        tc_id = tc["id"]
        eval_type = tc["evaluation_type"]
        expected = tc.get("expected_decision", "?")

        try:
            if eval_type == "asp_direct":
                mock_facts = tc["input"]["mock_facts"]
                out = run_asp_direct(mock_facts, baseline)
                actual = out["decision"]
            else:
                turns = tc["input"].get("turns", [tc["input"].get("query", "")])
                thread_id = f"bench-{baseline}-{tc_id}"
                if baseline == "A":
                    out = run_llm_only(turns)
                elif baseline == "B":
                    out = run_rag_only(turns, thread_id)
                else:
                    out = run_full_pipeline(turns, thread_id)
                actual = out["decision"]

            correct = (actual == expected)
            icon = "✅" if correct else "❌"
            print(f"  {icon} {tc_id} ({tc['category'][:20]:<20}) "
                  f"expected={expected:<22} got={actual}  {out['latency_ms']}ms")

            results.append({
                "test_id": tc_id,
                "category": tc["category"],
                "evaluation_type": eval_type,
                "description": tc["description"],
                "expected_decision": expected,
                "actual_decision": actual,
                "correct": correct,
                "latency_ms": out.get("latency_ms", 0),
                "violations": out.get("violations", []),
                "answer": out.get("answer", ""),
            })

        except Exception as e:
            print(f"  ⚠ {tc_id} ERROR: {type(e).__name__}: {str(e)[:60]}")
            results.append({
                "test_id": tc_id,
                "category": tc["category"],
                "evaluation_type": eval_type,
                "description": tc["description"],
                "expected_decision": expected,
                "actual_decision": "error",
                "correct": False,
                "latency_ms": 0,
                "error": str(e),
            })

    return results


def save_results(baseline: str, results: list[dict]) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"baseline_{baseline}_{ts}.json"
    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    latencies = [r["latency_ms"] for r in results if r["latency_ms"] > 0]

    summary = {
        "baseline": baseline,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0,
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
        "results": results,
    }
    with open(path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Saved → {path}  ({correct}/{total} correct, avg {summary['avg_latency_ms']}ms)")
    return path


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", choices=["A", "B", "C", "all"], default="all")
    args = parser.parse_args()

    with open(FIXTURE_PATH) as f:
        data = json.load(f)
    cases = data["test_cases"]

    to_run = ["A", "B", "C"] if args.baseline == "all" else [args.baseline]
    saved = {}

    for b in to_run:
        results = run_baseline(b, cases)
        saved[b] = save_results(b, results)

    if len(to_run) > 1:
        print(f"\n{'='*60}")
        print("  All baselines complete. Run analyze:")
        for b, p in saved.items():
            print(f"    python scripts/analyze_results.py --files {p}")

    from src.telemetry import _trace_provider
    _trace_provider.force_flush()


if __name__ == "__main__":
    main()
