"""
Empirical hallucination evaluation for the Cloudway.

Measures real hallucination rates for Baselines A, B, and C on 20 factual
questions derived directly from holiday_policy.lp (fee brackets, deadlines,
amendment fees, age limits). This is distinct from the ASP-direct evaluation
in benchmark_baselines.py, which tests the ASP detector with pre-injected facts.
This script tests whether each baseline's LLM generates correct factual values.

Methodology:
  1. Each question asks for a specific verifiable value (number, percentage, days).
  2. The question is run through the real baseline pipeline.
  3. A "claim extractor" LLM call reads the answer and pulls the stated value.
  4. Extracted value vs. gold standard → is_hallucination (True/False).
  5. For Baseline C only: cross-reference with pipeline decision to measure
     what fraction of hallucinations were caught (escalated) vs. slipped through.

Key metrics reported:
  - hallucination_rate:      fraction of questions where LLM stated a wrong value
  - evasion_rate:            fraction where LLM refused to state any value
  - false_approval_rate:     fraction of hallucinations that reached the customer
  - detection_rate (C only): fraction of hallucinations that Baseline C escalated

Outputs:
  logs/hallucination_eval_<timestamp>.json  — machine-readable full results
  logs/hallucination_eval_<timestamp>.txt   — human-readable summary table

Run:
    python scripts/hallucination_eval.py
    python scripts/hallucination_eval.py --baseline A
    python scripts/hallucination_eval.py --cases HT001,HT010,HT013
"""

import argparse, json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_aws import ChatBedrock
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.state import GuardrailsState
from src.agents.classifier import classifier_node
from src.graph import build_graph
from src.telemetry import TRACER
import src.agents.rag_agent as _ra
import src.agents.fact_extractor as _fe
from src.agents.rag_agent import rag_agent_node

# ── Normalize lowercase env var keys ─────────────────────────────────────────
for _k in list(os.environ.keys()):
    if _k.startswith(("aws_", "bedrock_")):
        os.environ.setdefault(_k.upper(), os.environ[_k])

_ra._llm = None
_ra._retriever = None
_fe._llm = None


# ── Early credential check ────────────────────────────────────────────────────
def _check_aws_credentials() -> None:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    try:
        boto3.client("sts", region_name=os.getenv("AWS_DEFAULT_REGION", "eu-central-1")).get_caller_identity()
    except ClientError as e:
        code = e.response["Error"]["Code"]
        print(f"\n❌  AWS error ({code}). Update credentials in .env\n")
        sys.exit(1)
    except NoCredentialsError:
        print("\n❌  No AWS credentials found. Check .env\n")
        sys.exit(1)

_check_aws_credentials()

FIXTURE_PATH = Path("tests/fixtures/hallucination_test_cases.json")
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


# ── LLM factory ───────────────────────────────────────────────────────────────
def _get_llm():
    return ChatBedrock(
        model_id=os.getenv("BEDROCK_LLM", "eu.anthropic.claude-sonnet-4-6"),
        region_name=os.getenv("AWS_DEFAULT_REGION", "eu-central-1"),
        model_kwargs={"temperature": 0, "max_tokens": 1000},
    )


def _get_extractor_llm():
    return ChatBedrock(
        model_id=os.getenv("BEDROCK_LLM", "eu.anthropic.claude-sonnet-4-6"),
        region_name=os.getenv("AWS_DEFAULT_REGION", "eu-central-1"),
        model_kwargs={"temperature": 0, "max_tokens": 50},
    )


# ── Claim extractor ───────────────────────────────────────────────────────────

_EXTRACTOR_SYSTEM = (
    "You are a value extractor. Given an answer text and an extraction instruction, "
    "you output ONLY the extracted value — a single number, or the string 'not_stated' "
    "if the answer does not state any specific value. Do not explain. Do not add units. "
    "Output nothing else."
)

def extract_claimed_value(answer: str, extract_prompt: str) -> str:
    """
    Calls the LLM to extract the specific numeric claim from an answer.
    Returns a string like '30', '0', '25', or 'not_stated'.
    """
    llm = _get_extractor_llm()
    user_msg = f"Answer text:\n{answer}\n\nExtraction instruction:\n{extract_prompt}"
    resp = llm.invoke([SystemMessage(content=_EXTRACTOR_SYSTEM), HumanMessage(content=user_msg)])
    return resp.content.strip()


def is_hallucination(extracted: str, gold_value: float, gold_unit: str) -> tuple[bool, str]:
    """
    Compares extracted claim against gold standard.
    Returns (is_hallucination, verdict) where verdict is one of:
      'correct', 'hallucination', 'evasion'

    Evasion = LLM said 'not_stated' / hedged / refused to give a number.
    Hallucination = stated a specific wrong value.
    """
    if extracted.lower() in ("not_stated", "not stated", "none", "n/a", ""):
        return (True, "evasion")

    # Extract numeric part from the response
    nums = re.findall(r"[-+]?\d*\.?\d+", extracted)
    if not nums:
        return (True, "evasion")

    claimed = float(nums[0])
    if claimed == float(gold_value):
        return (False, "correct")
    return (True, "hallucination")


# ── Baseline A: LLM Only ──────────────────────────────────────────────────────

_LLMONLY_SYSTEM = (
    "You are a holiday booking assistant. Answer customer questions "
    "about TUI holiday packages policy accurately and concisely. "
    "If you do not know, say you do not know."
)

def run_baseline_a(query: str) -> dict:
    llm = _get_llm()
    messages = [SystemMessage(content=_LLMONLY_SYSTEM), HumanMessage(content=query)]
    t0 = time.time()
    resp = llm.invoke(messages)
    latency_ms = int((time.time() - t0) * 1000)
    answer = resp.content
    lower = answer.lower()
    if any(kw in lower for kw in ["not covered", "don't have information", "cannot help", "out of scope"]):
        decision = "refused_out_of_scope"
    elif "?" in answer and len(answer) < 200:
        decision = "pending_info"
    else:
        decision = "approved"
    return {"answer": answer, "decision": decision, "latency_ms": latency_ms}


# ── Baseline B: RAG Only ──────────────────────────────────────────────────────

def _build_rag_only_graph():
    def rag_only_decision(state: GuardrailsState) -> dict:
        if state.get("classification_error", False):
            return {"decision": "escalated"}
        if state.get("is_clarification", False):
            return {"decision": "pending_info"}
        if state.get("is_refusal", False):
            return {"decision": "refused_out_of_scope"}
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

def run_baseline_b(query: str, thread_id: str) -> dict:
    global _rag_only_graph
    if _rag_only_graph is None:
        _rag_only_graph = _build_rag_only_graph()
    config = {"configurable": {"thread_id": thread_id}}
    t0 = time.time()
    result = _rag_only_graph.invoke({"messages": [HumanMessage(content=query)]}, config=config)
    latency_ms = int((time.time() - t0) * 1000)
    ai = [m for m in result["messages"] if hasattr(m, "type") and m.type == "ai"]
    return {
        "answer": ai[-1].content if ai else "",
        "decision": result.get("decision", "error"),
        "latency_ms": latency_ms,
    }


# ── Baseline C: RAG + ASP (full pipeline) ────────────────────────────────────

_full_graph = None

def run_baseline_c(query: str, thread_id: str) -> dict:
    global _full_graph
    if _full_graph is None:
        _full_graph = build_graph()
    config = {"configurable": {"thread_id": thread_id}}
    t0 = time.time()
    with TRACER.start_as_current_span("hallucination_eval.graph.run") as span:
        span.set_attribute("baseline", "C")
        span.set_attribute("thread_id", thread_id)
        result = _full_graph.invoke({"messages": [HumanMessage(content=query)]}, config=config)
    latency_ms = int((time.time() - t0) * 1000)
    ai = [m for m in result["messages"] if hasattr(m, "type") and m.type == "ai"]
    return {
        "answer": ai[-1].content if ai else "",
        "decision": result.get("decision", "error"),
        "violations": result.get("violations", []),
        "extracted_facts": result.get("extracted_facts", []),
        "latency_ms": latency_ms,
    }


# ── Per-case evaluation ───────────────────────────────────────────────────────

def evaluate_case(tc: dict, baselines: list[str]) -> dict:
    """
    Runs a single test case through each requested baseline and
    extracts/compares the claimed value.
    Returns a per-case result dict.
    """
    case_id = tc["id"]
    query = tc["query"]
    gold_value = tc["gold_value"]
    gold_unit = tc["gold_unit"]
    extract_prompt = tc["extract_prompt"]

    per_baseline = {}

    for bl in baselines:
        try:
            thread_id = f"halleval-{bl}-{case_id}"
            if bl == "A":
                out = run_baseline_a(query)
            elif bl == "B":
                out = run_baseline_b(query, thread_id)
            else:
                out = run_baseline_c(query, thread_id)

            answer = out["answer"]
            decision = out["decision"]

            # Claim extraction
            t0 = time.time()
            extracted = extract_claimed_value(answer, extract_prompt)
            extract_latency_ms = int((time.time() - t0) * 1000)

            hallucinated, verdict = is_hallucination(extracted, gold_value, gold_unit)

            # Detection (only meaningful for C, but compute for all)
            if hallucinated and decision == "escalated":
                detection_status = "caught"
            elif hallucinated and decision in ("approved", "pending_info"):
                detection_status = "missed"
            elif not hallucinated and decision == "escalated":
                detection_status = "over_escalated"
            else:
                detection_status = "passed_correctly"

            per_baseline[bl] = {
                "answer": answer,
                "decision": decision,
                "extracted_claim": extracted,
                "gold_value": gold_value,
                "gold_unit": gold_unit,
                "verdict": verdict,
                "is_hallucination": hallucinated,
                "detection_status": detection_status,
                "latency_ms": out["latency_ms"],
                "extract_latency_ms": extract_latency_ms,
                "violations": out.get("violations", []),
            }

            icon = "🔴" if hallucinated else "✅"
            print(
                f"    {icon} [{bl}] extracted={extracted!r:10s} gold={gold_value}  "
                f"verdict={verdict:<12}  decision={decision:<22}  {out['latency_ms']}ms"
            )

        except Exception as e:
            print(f"    ⚠ [{bl}] ERROR: {type(e).__name__}: {str(e)[:80]}")
            per_baseline[bl] = {
                "answer": "", "decision": "error", "extracted_claim": "error",
                "gold_value": gold_value, "gold_unit": gold_unit,
                "verdict": "error", "is_hallucination": True,
                "detection_status": "error",
                "latency_ms": 0, "extract_latency_ms": 0,
                "violations": [], "error": str(e),
            }

    return {
        "id": case_id,
        "category": tc["category"],
        "description": tc["description"],
        "query": query,
        "gold_value": gold_value,
        "gold_unit": gold_unit,
        "hallucination_note": tc.get("hallucination_note", ""),
        "baselines": per_baseline,
    }


# ── Aggregate metrics ─────────────────────────────────────────────────────────

def compute_metrics(results: list[dict], baselines: list[str]) -> dict:
    metrics = {}
    for bl in baselines:
        total = 0
        n_hallucination = 0
        n_evasion = 0
        n_correct = 0
        n_caught = 0
        n_missed = 0
        n_over_escalated = 0
        n_errors = 0

        for r in results:
            br = r["baselines"].get(bl, {})
            if br.get("verdict") == "error":
                n_errors += 1
                continue
            total += 1
            verdict = br["verdict"]
            det = br["detection_status"]
            if verdict == "correct":
                n_correct += 1
            elif verdict == "hallucination":
                n_hallucination += 1
            elif verdict == "evasion":
                n_evasion += 1

            if det == "caught":
                n_caught += 1
            elif det == "missed":
                n_missed += 1
            elif det == "over_escalated":
                n_over_escalated += 1

        n_any_error = n_hallucination + n_evasion  # anything not correct
        metrics[bl] = {
            "total_cases": total,
            "correct": n_correct,
            "hallucinations": n_hallucination,
            "evasions": n_evasion,
            "errors": n_errors,
            "hallucination_rate": round(n_hallucination / total, 4) if total else 0,
            "evasion_rate": round(n_evasion / total, 4) if total else 0,
            "accuracy": round(n_correct / total, 4) if total else 0,
            # false_approval_rate = fraction of ALL queries where a wrong value slipped through
            "false_approval_rate": round(n_missed / total, 4) if total else 0,
            # detection_rate = of hallucinations that occurred, how many did C catch?
            "detection_rate": round(n_caught / n_any_error, 4) if n_any_error else None,
            "caught": n_caught,
            "missed": n_missed,
            "over_escalated": n_over_escalated,
        }
    return metrics


# ── Output formatting ─────────────────────────────────────────────────────────

def print_summary(metrics: dict, baselines: list[str]) -> None:
    print(f"\n{'='*70}")
    print("  HALLUCINATION EVALUATION — SUMMARY")
    print(f"{'='*70}")
    header = f"{'Metric':<32}"
    for bl in baselines:
        header += f"{'Baseline ' + bl:>12}"
    print(header)
    print("-" * (32 + 12 * len(baselines)))

    rows = [
        ("Total cases", "total_cases", "d"),
        ("Correct (no hallucination)", "correct", "d"),
        ("Hallucinations (wrong value)", "hallucinations", "d"),
        ("Evasions (no value stated)", "evasions", "d"),
        ("Accuracy", "accuracy", "%"),
        ("Hallucination rate", "hallucination_rate", "%"),
        ("Evasion rate", "evasion_rate", "%"),
        ("False approval rate", "false_approval_rate", "%"),
        ("Detection rate (C only)", "detection_rate", "%"),
        ("Caught (escalated) by C", "caught", "d"),
        ("Missed (approved) by C", "missed", "d"),
    ]

    for label, key, fmt in rows:
        row = f"  {label:<30}"
        for bl in baselines:
            val = metrics.get(bl, {}).get(key)
            if val is None:
                row += f"{'—':>12}"
            elif fmt == "%":
                row += f"{val * 100:>11.1f}%"
            else:
                row += f"{val:>12}"
        print(row)

    print(f"{'='*70}")
    print()


def write_summary_txt(path: Path, metrics: dict, baselines: list[str], results: list[dict]) -> None:
    lines = ["CLOUDWAY — HALLUCINATION EVALUATION", "=" * 70, ""]
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Baselines tested: {', '.join(baselines)}")
    lines.append(f"Test cases: {len(results)}")
    lines.append("")
    lines.append("METRICS TABLE")
    lines.append("-" * 70)
    header = f"{'Metric':<32}"
    for bl in baselines:
        header += f"{'Baseline ' + bl:>12}"
    lines.append(header)
    lines.append("-" * (32 + 12 * len(baselines)))

    rows = [
        ("Total cases", "total_cases", "d"),
        ("Correct (no hallucination)", "correct", "d"),
        ("Hallucinations (wrong value)", "hallucinations", "d"),
        ("Evasions (no value stated)", "evasions", "d"),
        ("Accuracy", "accuracy", "%"),
        ("Hallucination rate", "hallucination_rate", "%"),
        ("Evasion rate", "evasion_rate", "%"),
        ("False approval rate", "false_approval_rate", "%"),
        ("Detection rate (C only)", "detection_rate", "%"),
        ("Caught (escalated) by C", "caught", "d"),
        ("Missed (approved) by C", "missed", "d"),
    ]
    for label, key, fmt in rows:
        row = f"  {label:<30}"
        for bl in baselines:
            val = metrics.get(bl, {}).get(key)
            if val is None:
                row += f"{'—':>12}"
            elif fmt == "%":
                row += f"{val * 100:>11.1f}%"
            else:
                row += f"{val:>12}"
        lines.append(row)

    lines.append("")
    lines.append("PER-CASE RESULTS")
    lines.append("-" * 70)
    for r in results:
        lines.append(f"\n[{r['id']}] {r['description']}")
        lines.append(f"  Query: {r['query']}")
        lines.append(f"  Gold:  {r['gold_value']} {r['gold_unit']}")
        for bl in baselines:
            br = r["baselines"].get(bl, {})
            lines.append(
                f"  [{bl}] extracted={br.get('extracted_claim', '?')!r:<10}  "
                f"verdict={br.get('verdict', '?'):<12}  "
                f"decision={br.get('decision', '?'):<20}  "
                f"detection={br.get('detection_status', '?')}"
            )
        lines.append(f"  Note: {r.get('hallucination_note', '')}")

    with open(path, "w") as f:
        f.write("\n".join(lines))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Empirical hallucination evaluation")
    parser.add_argument("--baseline", choices=["A", "B", "C", "all"], default="all",
                        help="Which baselines to run (default: all)")
    parser.add_argument("--cases", default="",
                        help="Comma-separated case IDs to run (e.g. HT001,HT010). Empty = all.")
    args = parser.parse_args()

    baselines = ["A", "B", "C"] if args.baseline == "all" else [args.baseline]
    filter_ids = set(args.cases.split(",")) if args.cases else set()

    with open(FIXTURE_PATH) as f:
        data = json.load(f)

    test_cases = data["test_cases"]
    if filter_ids:
        test_cases = [tc for tc in test_cases if tc["id"] in filter_ids]

    print(f"\n{'='*70}")
    print(f"  Cloudway Hallucination Evaluation")
    print(f"  Cases: {len(test_cases)}   Baselines: {', '.join(baselines)}")
    print(f"{'='*70}\n")

    all_results = []
    for tc in test_cases:
        print(f"\n[{tc['id']}] {tc['description']}")
        print(f"  Query: {tc['query'][:80]}")
        result = evaluate_case(tc, baselines)
        all_results.append(result)

    metrics = compute_metrics(all_results, baselines)
    print_summary(metrics, baselines)

    # Save outputs
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = LOG_DIR / f"hallucination_eval_{ts}.json"
    txt_path = LOG_DIR / f"hallucination_eval_{ts}.txt"

    payload = {
        "version": "1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "baselines": baselines,
        "total_cases": len(all_results),
        "metrics": metrics,
        "results": all_results,
    }
    with open(json_path, "w") as f:
        json.dump(payload, f, indent=2)

    write_summary_txt(txt_path, metrics, baselines, all_results)

    print(f"  Saved JSON  → {json_path}")
    print(f"  Saved TXT   → {txt_path}\n")

    from src.telemetry import _trace_provider
    _trace_provider.force_flush()


if __name__ == "__main__":
    main()
