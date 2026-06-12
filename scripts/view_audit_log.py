"""
View audit log records.

Usage:
    python scripts/view_audit_log.py              # last 20 records
    python scripts/view_audit_log.py --thread session-001
    python scripts/view_audit_log.py --stats
"""

import sys, json, argparse
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.persistence.audit_log import query_logs

SEP = "-" * 65

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--thread", help="Filter by thread_id")
    parser.add_argument("--stats", action="store_true", help="Show summary stats")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    records = query_logs(thread_id=args.thread, limit=args.limit)

    if not records:
        print("No audit records found. Run the pipeline first.")
        return

    if args.stats:
        decisions = Counter(r["decision"] for r in records)
        latencies = [r["latency_ms"] for r in records if r.get("latency_ms")]
        print(f"\n{'='*40}")
        print(f"  Audit Log Stats ({len(records)} records)")
        print(f"{'='*40}")
        for decision, count in decisions.most_common():
            pct = count / len(records) * 100
            print(f"  {decision:<25} {count:3d}  ({pct:.0f}%)")
        if latencies:
            print(f"\n  Avg latency:  {sum(latencies)/len(latencies):.0f}ms")
            print(f"  Min latency:  {min(latencies)}ms")
            print(f"  Max latency:  {max(latencies)}ms")
        print()
        return

    print(f"\nLast {len(records)} audit records:\n")
    for r in records:
        ts = r.get("timestamp","")[:19]
        decision = r.get("decision","?")
        icon = {"approved":"✅","refused_out_of_scope":"↷","escalated":"⚠","pending_info":"…"}.get(decision,"?")
        print(f"{icon} [{ts}] thread={r.get('thread_id','')}  decision={decision}  latency={r.get('latency_ms','?')}ms")
        print(f"   Q: {r.get('user_query','')[:80]}")
        if r.get("violations"):
            print(f"   violations: {r['violations'][:2]}")
        if r.get("extracted_facts"):
            print(f"   facts: {r['extracted_facts'][:2]}")
        print()

if __name__ == "__main__":
    main()
