"""
Compute thesis metrics from baseline result files.

Usage:
    python scripts/analyze_results.py
    python scripts/analyze_results.py --files logs/baseline_A_*.json logs/baseline_C_*.json

Metrics computed (per Master Thesis Guide Section 16.2):
  - Policy Compliance Accuracy:  % decisions matching expected
  - Hallucination Detection Rate: % of hallucination cases caught (escalated)
  - False Accept Rate:            % of hallucination cases incorrectly approved
  - Escalation Rate:              % of all queries escalated
  - Avg Latency (ms)
"""

import argparse, json, glob
from pathlib import Path
from collections import Counter

HALLUCINATION_IDS = {"TC005", "TC014", "TC024", "TC025"}
SLOT_DETECTION_IDS = {"TC010", "TC021", "TC022"}

def load_latest_per_baseline(log_dir: Path) -> dict[str, dict]:
    """Load the most recent result file for each baseline."""
    files = {}
    for b in ("A", "B", "C"):
        matches = sorted(glob.glob(str(log_dir / f"baseline_{b}_*.json")))
        if matches:
            with open(matches[-1]) as f:
                files[b] = json.load(f)
    return files


def compute_metrics(data: dict) -> dict:
    results = data["results"]
    total = len(results)
    if total == 0:
        return {}

    # Overall accuracy
    correct = sum(1 for r in results if r["correct"])
    accuracy = correct / total

    # Hallucination detection
    hall = [r for r in results if r["test_id"] in HALLUCINATION_IDS]
    detected = sum(1 for r in hall if r["actual_decision"] == "escalated")
    hall_detection_rate = detected / len(hall) if hall else 0
    false_accept_rate = 1 - hall_detection_rate

    # Escalation rate (real-pipeline cases only)
    real = [r for r in results if r.get("evaluation_type") != "asp_direct"]
    escalated = sum(1 for r in real if r["actual_decision"] == "escalated")
    escalation_rate = escalated / len(real) if real else 0

    # Slot detection (pending_info accuracy)
    slot = [r for r in results if r["test_id"] in SLOT_DETECTION_IDS]
    slot_correct = sum(1 for r in slot if r["correct"])
    slot_accuracy = slot_correct / len(slot) if slot else 0

    # Latency
    latencies = [r["latency_ms"] for r in results if r.get("latency_ms", 0) > 0]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    # Decision breakdown
    decisions = Counter(r["actual_decision"] for r in results)

    return {
        "total": total,
        "accuracy": accuracy,
        "hallucination_detection_rate": hall_detection_rate,
        "false_accept_rate": false_accept_rate,
        "escalation_rate": escalation_rate,
        "slot_detection_accuracy": slot_accuracy,
        "avg_latency_ms": avg_latency,
        "decisions": dict(decisions),
        "hallucination_cases": len(hall),
        "hallucination_detected": detected,
    }


def print_report(baselines: dict[str, dict]):
    metrics = {b: compute_metrics(d) for b, d in baselines.items()}

    labels = {
        "A": "LLM Only",
        "B": "RAG Only",
        "C": "RAG + ASP (Cloudway)",
    }

    W = 22

    def row(label, key, fmt=".1%", suffix=""):
        vals = []
        for b in ("A", "B", "C"):
            if b in metrics and key in metrics[b]:
                v = metrics[b][key]
                vals.append(f"{v:{fmt}}{suffix}")
            else:
                vals.append("  N/A  ")
        print(f"  {label:<35} " + "   ".join(f"{v:>{W}}" for v in vals))

    def divider():
        print("  " + "-" * (35 + 3 * (W + 3)))

    # Header
    print()
    print("=" * 80)
    print("  CLOUDWAY — THESIS EVALUATION RESULTS")
    print("=" * 80)
    print(f"  {'Metric':<35} " + "   ".join(f"{labels.get(b, b):>{W}}" for b in ("A", "B", "C") if b in metrics))
    divider()

    row("Policy Compliance Accuracy",    "accuracy",                   ".1%")
    row("Hallucination Detection Rate",  "hallucination_detection_rate",".1%")
    row("False Accept Rate",             "false_accept_rate",           ".1%")
    row("Slot Detection Accuracy",       "slot_detection_accuracy",     ".1%")
    row("Escalation Rate",               "escalation_rate",             ".1%")
    row("Avg Latency (ms)",              "avg_latency_ms",              ".0f","ms")
    divider()

    # Decision breakdown
    print()
    print("  Decision Breakdown:")
    all_decisions = set()
    for m in metrics.values():
        all_decisions.update(m.get("decisions", {}).keys())
    for d in sorted(all_decisions):
        vals = []
        for b in ("A", "B", "C"):
            if b in metrics:
                count = metrics[b].get("decisions", {}).get(d, 0)
                total = metrics[b]["total"]
                vals.append(f"{count}/{total} ({count/total:.0%})")
            else:
                vals.append("N/A")
        print(f"  {'  '+d:<35} " + "   ".join(f"{v:>{W}}" for v in vals))

    # Hallucination case detail
    print()
    print("  Hallucination Cases (RQ1):")
    for b, data in baselines.items():
        hall_results = [r for r in data["results"] if r["test_id"] in HALLUCINATION_IDS]
        if hall_results:
            detected = [r["test_id"] for r in hall_results if r["actual_decision"] == "escalated"]
            missed   = [r["test_id"] for r in hall_results if r["actual_decision"] != "escalated"]
            print(f"    Baseline {b} ({labels[b]})")
            print(f"      Detected (escalated): {detected}")
            print(f"      Missed   (approved):  {missed}")

    print()
    print("=" * 80)
    print("  Key Finding:")
    if "C" in metrics and "A" in metrics:
        c_acc = metrics["C"]["accuracy"]
        a_acc = metrics["A"]["accuracy"]
        c_det = metrics["C"]["hallucination_detection_rate"]
        a_det = metrics["A"]["hallucination_detection_rate"]
        print(f"    Accuracy improvement (A→C):              {c_acc - a_acc:+.1%}")
        print(f"    Hallucination detection improvement (A→C): {c_det - a_det:+.1%}")
    print("=" * 80)
    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="*", help="Specific result files to analyze")
    args = parser.parse_args()

    log_dir = Path("logs")

    if args.files:
        baselines = {}
        for f in args.files:
            with open(f) as fh:
                d = json.load(fh)
            baselines[d["baseline"]] = d
    else:
        baselines = load_latest_per_baseline(log_dir)

    if not baselines:
        print("No result files found. Run: python scripts/benchmark_baselines.py")
        return

    print_report(baselines)

    # Save combined report
    ts = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = log_dir / f"evaluation_report_{ts}.json"
    with open(report_path, "w") as f:
        json.dump({
            b: compute_metrics(d) for b, d in baselines.items()
        }, f, indent=2)
    print(f"  Metrics saved to: {report_path}")


if __name__ == "__main__":
    main()
