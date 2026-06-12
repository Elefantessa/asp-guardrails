"""
Cloudway — Human Review Interface

Shows escalated cases from the audit log.
Reviewer can Approve or Reject each case.

Run on a different port:
    streamlit run src/ui/review_app.py --server.port 8502
"""

import os, sys, json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Cloudway — Human Review",
    page_icon="⚠️",
    layout="wide",
)

st.markdown("""
<style>
.violation-pill { display:inline-block; background:#fdecea; border:1px solid #f5c6cb;
                  border-radius:3px; padding:2px 8px; font-family:monospace;
                  font-size:0.8em; margin:2px; }
.fact-pill { display:inline-block; background:#e8f4f8; border:1px solid #b8daff;
             border-radius:3px; padding:2px 8px; font-family:monospace;
             font-size:0.8em; margin:2px; }
</style>
""", unsafe_allow_html=True)

AUDIT_PATH = Path("logs/audit.jsonl")
REVIEW_PATH = Path("logs/review_decisions.jsonl")


def load_escalated() -> list[dict]:
    if not AUDIT_PATH.exists():
        return []
    records = []
    with open(AUDIT_PATH) as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("decision") == "escalated":
                    records.append(r)
            except json.JSONDecodeError:
                continue
    return records


def load_reviewed() -> set[str]:
    reviewed = set()
    if REVIEW_PATH.exists():
        with open(REVIEW_PATH) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    reviewed.add(r.get("record_key", ""))
                except json.JSONDecodeError:
                    continue
    return reviewed


def save_decision(record: dict, verdict: str, reviewer_note: str):
    REVIEW_PATH.parent.mkdir(exist_ok=True)
    entry = {
        "record_key": f"{record['thread_id']}_{record['timestamp']}",
        "thread_id": record["thread_id"],
        "timestamp": record["timestamp"],
        "user_query": record["user_query"],
        "verdict": verdict,
        "reviewer_note": reviewer_note,
        "reviewed_at": datetime.utcnow().isoformat(),
    }
    with open(REVIEW_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ── Page ──────────────────────────────────────────────────────────────────────

st.title("⚠️ Escalated Cases — Human Review")
st.caption("Review answers that failed ASP validation before showing them to users.")

escalated = load_escalated()
reviewed  = load_reviewed()
pending   = [r for r in escalated
             if f"{r['thread_id']}_{r['timestamp']}" not in reviewed]

col1, col2, col3 = st.columns(3)
col1.metric("Total escalated", len(escalated))
col2.metric("Pending review", len(pending))
col3.metric("Reviewed", len(escalated) - len(pending))

if not escalated:
    st.info("No escalated cases yet. Run the pipeline to generate some.")
    st.stop()

st.divider()

tab1, tab2 = st.tabs(["⏳ Pending", "✅ Reviewed"])

with tab1:
    if not pending:
        st.success("All escalated cases have been reviewed.")
    for record in pending:
        key = f"{record['thread_id']}_{record['timestamp']}"
        ts  = record.get("timestamp", "")[:19].replace("T", " ")

        with st.expander(f"[{ts}]  {record['user_query'][:80]}", expanded=True):
            c1, c2 = st.columns([2, 1])

            with c1:
                st.markdown("**User query:**")
                st.info(record["user_query"])

                st.markdown("**LLM answer:**")
                display = "\n".join(
                    ln for ln in record["llm_answer"].splitlines()
                    if not ln.strip().startswith(("CLAIM:", "REFUSAL:"))
                ).strip() or record["llm_answer"]
                st.warning(display)

            with c2:
                st.markdown("**Session:** `" + record.get("thread_id", "") + "`")
                st.markdown(f"**Latency:** {record.get('latency_ms', '?')} ms")

                viol = record.get("violations", [])
                if viol:
                    st.markdown("**ASP Violations:**")
                    for v in viol:
                        st.markdown(f'<span class="violation-pill">{v}</span>',
                                    unsafe_allow_html=True)

                facts = record.get("extracted_facts", [])
                if facts:
                    st.markdown("**Extracted facts:**")
                    for f in facts:
                        st.markdown(f'<span class="fact-pill">{f}</span>',
                                    unsafe_allow_html=True)

            note = st.text_input("Reviewer note (optional)", key=f"note_{key}")
            b1, b2 = st.columns(2)
            if b1.button("✅ Approve — answer is correct", key=f"approve_{key}", type="primary"):
                save_decision(record, "approved", note)
                st.success("Saved as approved.")
                st.rerun()
            if b2.button("❌ Reject — answer is wrong", key=f"reject_{key}"):
                save_decision(record, "rejected", note)
                st.error("Saved as rejected.")
                st.rerun()

with tab2:
    if not REVIEW_PATH.exists():
        st.info("No review decisions yet.")
    else:
        decisions = []
        with open(REVIEW_PATH) as f:
            for line in f:
                try:
                    decisions.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        for d in reversed(decisions):
            icon = "✅" if d["verdict"] == "approved" else "❌"
            ts   = d.get("reviewed_at", "")[:19].replace("T", " ")
            st.markdown(
                f"{icon} `[{ts}]` **{d['user_query'][:60]}** — {d['verdict'].upper()}"
                + (f" — _{d['reviewer_note']}_" if d.get("reviewer_note") else "")
            )
