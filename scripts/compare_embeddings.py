"""
Embedding Comparison — D4

Runs all 31 test cases (TC001–TC031) against both embedding backends and
produces a side-by-side comparison report.

Outputs:
  evaluation/embedding_comparison.json
  evaluation/embedding_comparison_report.md

Run:
    python scripts/compare_embeddings.py
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

# Normalize lowercase env var keys (dotenv writes aws_* in lowercase on some platforms)
for _k in list(os.environ.keys()):
    if _k.startswith(("aws_", "bedrock_")):
        os.environ.setdefault(_k.upper(), os.environ[_k])

import src.agents.rag_agent as _ra
import src.agents.fact_extractor as _fe
import src.agents.query_rewriter as _qr

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from src.graph import build_graph
from src.agents.asp_validator import asp_validator_node
from src.state import GuardrailsState
from src.telemetry import TRACER

FIXTURE_PATH = Path("tests/fixtures/test_cases.json")
EVAL_DIR     = Path("evaluation")
EVAL_DIR.mkdir(exist_ok=True)


# ── AWS credential check ──────────────────────────────────────────────────────

def _check_aws_credentials() -> None:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    try:
        region = os.getenv("AWS_DEFAULT_REGION", "eu-central-1")
        boto3.client("sts", region_name=region).get_caller_identity()
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("ExpiredTokenException", "ExpiredToken"):
            print("\n❌  AWS credentials expired. Update .env and retry.\n")
        else:
            print(f"\n❌  AWS error ({code}): {e}\n")
        sys.exit(1)
    except NoCredentialsError:
        print("\n❌  No AWS credentials found. Check .env\n")
        sys.exit(1)

_check_aws_credentials()


# ── Per-backend pipeline runner ───────────────────────────────────────────────

_graph_cache: dict[str, object] = {}


def _reset_singletons(backend: str) -> None:
    """Reset all agent module-level singletons so the next call builds fresh."""
    os.environ["EMBEDDING_BACKEND"] = backend
    _ra._llm         = None
    _ra._vectorstore = None
    _fe._llm         = None
    _qr._llm         = None
    # Clear cached graph for this backend (forces rebuild_graph with new vectorstore)
    _graph_cache.pop(backend, None)


def _get_graph(backend: str):
    if backend not in _graph_cache:
        _graph_cache[backend] = build_graph()
    return _graph_cache[backend]


def run_real_pipeline(turns: list[str], thread_id: str, backend: str) -> dict:
    graph  = _get_graph(backend)
    config = {"configurable": {"thread_id": thread_id}}
    result = None
    t0     = time.time()
    for turn in turns:
        with TRACER.start_as_current_span("compare.graph.run") as span:
            span.set_attribute("backend", backend)
            result = graph.invoke(
                {"messages": [HumanMessage(content=turn)]}, config=config
            )
    latency_ms = int((time.time() - t0) * 1000)

    ai_msgs = [m for m in result["messages"] if hasattr(m, "type") and m.type == "ai"]
    answer  = ai_msgs[-1].content if ai_msgs else ""

    scores  = result.get("retrieval_scores", [])
    min_score = round(min(scores), 4) if scores else None
    chunks  = result.get("retrieved_docs", [])
    chunk_count = len(chunks)

    return {
        "decision":    result.get("decision", "error"),
        "latency_ms":  latency_ms,
        "min_score":   min_score,
        "chunk_count": chunk_count,
        "violations":  result.get("violations", []),
        "answer":      answer[:300],
    }


def run_asp_direct(mock_facts: list[str]) -> dict:
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
    return {
        "decision":    "escalated" if not asp_result["validation_passed"] else "approved",
        "latency_ms":  latency_ms,
        "min_score":   None,
        "chunk_count": 0,
        "violations":  asp_result["violations"],
        "answer":      "",
    }


# ── Main comparison loop ──────────────────────────────────────────────────────

def run_backend(cases: list[dict], backend: str) -> list[dict]:
    label = "Bedrock (Titan v2)" if backend == "bedrock" else "HuggingFace (MiniLM)"
    print(f"\n{'='*60}")
    print(f"  Backend: {label}")
    print(f"{'='*60}")

    _reset_singletons(backend)
    results = []

    for tc in cases:
        tc_id     = tc["id"]
        eval_type = tc["evaluation_type"]
        expected  = tc.get("expected_decision", "?")

        try:
            if eval_type == "asp_direct":
                out = run_asp_direct(tc["input"]["mock_facts"])
                # asp_direct is backend-independent — latency is near-zero
            else:
                turns     = tc["input"].get("turns", [tc["input"].get("query", "")])
                thread_id = f"compare-{backend}-{tc_id}"
                out       = run_real_pipeline(turns, thread_id, backend)

            actual  = out["decision"]
            correct = (actual == expected)
            icon    = "✅" if correct else "❌"
            score_str = f"  score={out['min_score']}" if out["min_score"] is not None else ""
            print(f"  {icon} {tc_id:<6} expected={expected:<22} got={actual}  "
                  f"{out['latency_ms']}ms{score_str}")

            results.append({
                "id":        tc_id,
                "correct":   correct,
                **out,
            })

        except Exception as e:
            print(f"  ⚠ {tc_id} ERROR: {type(e).__name__}: {str(e)[:80]}")
            results.append({
                "id":         tc_id,
                "correct":    False,
                "decision":   "error",
                "latency_ms": 0,
                "min_score":  None,
                "chunk_count": 0,
                "violations": [],
                "answer":     "",
                "error":      str(e),
            })

    return results


# ── Report generation ─────────────────────────────────────────────────────────

def _summary(results: list[dict], backend: str) -> dict:
    correct   = sum(1 for r in results if r["correct"])
    latencies = [r["latency_ms"] for r in results if r["latency_ms"] > 0]
    scores    = [r["min_score"]  for r in results if r["min_score"]  is not None]
    return {
        "backend":       backend,
        "accuracy":      f"{correct}/{len(results)}",
        "accuracy_pct":  round(correct / len(results) * 100, 1) if results else 0,
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
        "avg_min_score": round(sum(scores) / len(scores), 4) if scores else None,
    }


def build_json_report(
    cases:   list[dict],
    bedrock: list[dict],
    hf:      list[dict],
) -> dict:
    per_case = []
    for tc, bd, hf_r in zip(cases, bedrock, hf):
        per_case.append({
            "id":          tc["id"],
            "category":    tc["category"],
            "query":       tc["input"].get("query", tc["input"].get("turns", [""])[0])[:120],
            "expected":    tc.get("expected_decision", "?"),
            "bedrock":     {k: bd[k] for k in ("decision","correct","latency_ms","min_score","chunk_count","violations")},
            "huggingface": {k: hf_r[k] for k in ("decision","correct","latency_ms","min_score","chunk_count","violations")},
            "agree":       bd["decision"] == hf_r["decision"],
        })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "bedrock":     _summary(bedrock, "bedrock"),
            "huggingface": _summary(hf,      "huggingface"),
        },
        "per_case": per_case,
    }


def build_md_report(report: dict) -> str:
    bd  = report["summary"]["bedrock"]
    hf  = report["summary"]["huggingface"]
    gen = report["generated_at"]

    lines = [
        "# Embedding Comparison Report",
        f"\n_Generated: {gen}_\n",
        "## Summary\n",
        "| Metric | Bedrock (Titan v2) | HuggingFace (MiniLM) |",
        "|---|---|---|",
        f"| Accuracy | {bd['accuracy']} ({bd['accuracy_pct']}%) | {hf['accuracy']} ({hf['accuracy_pct']}%) |",
        f"| Avg latency | {bd['avg_latency_ms']} ms | {hf['avg_latency_ms']} ms |",
        f"| Avg min similarity score | {bd['avg_min_score']} | {hf['avg_min_score']} |",
        "",
        "## Per-Case Results\n",
        "| ID | Category | Expected | Bedrock | HF | Agree | BD ms | HF ms | BD score | HF score |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    for c in report["per_case"]:
        bd_r = c["bedrock"]
        hf_r = c["huggingface"]
        bd_icon  = "✅" if bd_r["correct"] else "❌"
        hf_icon  = "✅" if hf_r["correct"] else "❌"
        agree    = "✓" if c["agree"] else "**✗**"
        bd_score = str(bd_r["min_score"]) if bd_r["min_score"] is not None else "—"
        hf_score = str(hf_r["min_score"]) if hf_r["min_score"] is not None else "—"
        lines.append(
            f"| {c['id']} | {c['category'][:18]} | {c['expected'][:18]} "
            f"| {bd_icon} {bd_r['decision'][:12]} "
            f"| {hf_icon} {hf_r['decision'][:12]} "
            f"| {agree} "
            f"| {bd_r['latency_ms']} | {hf_r['latency_ms']} "
            f"| {bd_score} | {hf_score} |"
        )

    # Disagreements section
    disagree = [c for c in report["per_case"] if not c["agree"]]
    if disagree:
        lines += [
            "\n## Backend Disagreements\n",
            "Cases where Bedrock and HuggingFace reached different decisions:\n",
            "| ID | Query | Expected | Bedrock | HuggingFace |",
            "|---|---|---|---|---|",
        ]
        for c in disagree:
            lines.append(
                f"| {c['id']} | {c['query'][:60]}… "
                f"| {c['expected']} "
                f"| {c['bedrock']['decision']} "
                f"| {c['huggingface']['decision']} |"
            )
    else:
        lines.append("\n## Backend Disagreements\n\nNone — both backends reached identical decisions on all cases. ✅")

    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    with open(FIXTURE_PATH) as f:
        data = json.load(f)
    cases = data["test_cases"]

    print(f"\nComparing embeddings on {len(cases)} test cases…")

    bedrock_results = run_backend(cases, "bedrock")
    hf_results      = run_backend(cases, "huggingface")

    report = build_json_report(cases, bedrock_results, hf_results)

    json_path = EVAL_DIR / "embedding_comparison.json"
    md_path   = EVAL_DIR / "embedding_comparison_report.md"

    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)

    md_path.write_text(build_md_report(report), encoding="utf-8")

    bd  = report["summary"]["bedrock"]
    hf  = report["summary"]["huggingface"]

    print(f"\n{'='*60}")
    print("  Comparison complete")
    print(f"{'='*60}")
    print(f"  Bedrock:     {bd['accuracy']} ({bd['accuracy_pct']}%)  avg {bd['avg_latency_ms']}ms  score={bd['avg_min_score']}")
    print(f"  HuggingFace: {hf['accuracy']} ({hf['accuracy_pct']}%)  avg {hf['avg_latency_ms']}ms  score={hf['avg_min_score']}")
    disagree_count = sum(1 for c in report["per_case"] if not c["agree"])
    print(f"  Disagreements: {disagree_count}/{len(cases)}")
    print(f"\n  Saved → {json_path}")
    print(f"  Saved → {md_path}")

    TRACER.force_flush() if hasattr(TRACER, "force_flush") else None


if __name__ == "__main__":
    main()
