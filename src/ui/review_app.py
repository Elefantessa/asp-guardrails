"""
Cloudway — Human Review Dashboard (Corporate UI)

Run:
    streamlit run src/ui/review_app.py --server.port 8502
"""

import os, sys, json
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Cloudway · Review Dashboard",
    page_icon="⚠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

*, html, body { box-sizing: border-box; }
html, body, [class*="css"], .stApp {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    background-color: #F8FAFC !important;
}

/* ── Hide Streamlit chrome ── */
#MainMenu, header[data-testid="stHeader"], footer,
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"] { display: none !important; visibility: hidden !important; }

.main .block-container { padding: 1.5rem 2rem 2rem !important; max-width: 1100px !important; }

/* ── Case cards: st.container(border=True) ── */
[data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid #E2E8F0 !important;
    border-radius: 10px !important;
    background: #FFFFFF !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05) !important;
    padding: 4px 4px !important;
    margin-bottom: 12px !important;
}

/* ── Tabs ── */
[data-testid="stTabs"] [role="tablist"] {
    border-bottom: 2px solid #E2E8F0 !important;
    gap: 0 !important; background: transparent !important;
}
[data-testid="stTabs"] button[role="tab"] {
    font-size: 0.82rem !important; font-weight: 500 !important;
    color: #64748B !important; padding: 8px 18px !important;
    border-radius: 0 !important; border: none !important; background: transparent !important;
}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: #1D4ED8 !important; font-weight: 600 !important;
    border-bottom: 2px solid #1D4ED8 !important;
}

/* ── Metric cards ── */
[data-testid="metric-container"] {
    background: #FFFFFF !important; border: 1px solid #E2E8F0 !important;
    border-radius: 10px !important; padding: 16px 20px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
}
[data-testid="metric-container"] label {
    font-size: 0.72rem !important; font-weight: 600 !important;
    text-transform: uppercase !important; letter-spacing: 0.06em !important;
    color: #94A3B8 !important;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-size: 2rem !important; font-weight: 700 !important; color: #0F172A !important;
}

/* ── Buttons ── */
[data-testid="stBaseButton-primary"] {
    background: #1D4ED8 !important; color: white !important;
    border: none !important; border-radius: 7px !important;
    font-size: 0.82rem !important; font-weight: 600 !important; padding: 8px 16px !important;
}
[data-testid="stBaseButton-primary"]:hover { background: #1E40AF !important; }

[data-testid="stBaseButton-secondary"] {
    background: white !important; border: 1.5px solid #E2E8F0 !important;
    color: #475569 !important; border-radius: 7px !important;
    font-size: 0.82rem !important; font-weight: 500 !important;
}
[data-testid="stBaseButton-secondary"]:hover {
    border-color: #F43F5E !important; color: #BE123C !important; background: #FFF1F2 !important;
}

/* ── Expanders inside cards ── */
[data-testid="stExpander"] {
    border: 1px solid #F1F5F9 !important; border-radius: 7px !important;
    background: #F8FAFC !important;
}
[data-testid="stExpander"] summary {
    font-size: 0.78rem !important; font-weight: 500 !important;
    color: #64748B !important; padding: 7px 12px !important;
}

/* ── Text input ── */
[data-testid="stTextInput"] input {
    border: 1.5px solid #E2E8F0 !important; border-radius: 7px !important;
    font-size: 0.83rem !important; padding: 7px 12px !important;
    background: #FFFFFF !important; color: #0F172A !important;
}
[data-testid="stTextInput"] input:focus {
    border-color: #1D4ED8 !important;
    box-shadow: 0 0 0 3px rgba(29,78,216,0.10) !important;
}

hr { border-color: #E2E8F0 !important; }

/* ── Custom HTML helpers ── */
.cw-navbar {
    display:flex; align-items:center;
    background:#FFFFFF; border:1px solid #E2E8F0; border-radius:10px;
    padding:12px 20px; margin-bottom:20px;
    box-shadow:0 1px 3px rgba(0,0,0,0.06);
}
.cw-navbar-brand    { font-size:1.05rem; font-weight:700; color:#0F172A; letter-spacing:-0.02em; }
.cw-navbar-sep      { color:#CBD5E1; margin:0 8px; }
.cw-navbar-subtitle { font-size:0.78rem; color:#64748B; }
.cw-navbar-link     {
    margin-left:auto; font-size:0.78rem; color:#1D4ED8; text-decoration:none;
    font-weight:500; background:#EFF6FF; border:1px solid #BFDBFE;
    border-radius:6px; padding:4px 12px;
}

.cw-badge {
    display:inline-flex; align-items:center;
    border-radius:4px; padding:2px 8px; margin:2px 2px 2px 0;
    font-size:0.70rem; font-weight:500; border:1px solid;
    font-family:'JetBrains Mono','Fira Code','Courier New',monospace; white-space:nowrap;
}
.cw-badge-fact      { background:#EFF6FF; border-color:#BFDBFE; color:#1D4ED8; }
.cw-badge-violation { background:#FFF1F2; border-color:#FECDD3; color:#BE123C; }

.cw-case-query   { font-size:0.92rem; font-weight:600; color:#0F172A; margin:0 0 3px; }
.cw-case-meta    { font-size:0.72rem; color:#94A3B8; margin:0 0 10px; }
.cw-answer-box   {
    background:#F8FAFC; border:1px solid #E2E8F0; border-radius:7px;
    padding:10px 14px; font-size:0.83rem; color:#334155;
    white-space:pre-wrap; word-break:break-word; line-height:1.55; margin:4px 0 8px;
}
.cw-field-label  { font-size:0.68rem; font-weight:700; letter-spacing:0.06em;
                   text-transform:uppercase; color:#94A3B8; margin:8px 0 4px; }
.cw-chunk-text   { font-size:0.75rem; color:#64748B; line-height:1.4; margin:2px 0 8px; }

.cw-reviewed-row {
    display:flex; align-items:flex-start; gap:10px;
    padding:10px 14px; border-radius:8px; margin:4px 0; font-size:0.83rem;
}
.cw-reviewed-query { flex:1; font-weight:500; color:#0F172A; }
.cw-reviewed-ts    { font-size:0.70rem; color:#94A3B8; white-space:nowrap; }
.cw-reviewed-note  { font-size:0.78rem; color:#64748B; font-style:italic; margin:2px 0 0 28px; }
</style>
""", unsafe_allow_html=True)

AUDIT_PATH  = Path("logs/audit.jsonl")
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


def load_reviewed_keys() -> set[str]:
    reviewed: set[str] = set()
    if REVIEW_PATH.exists():
        with open(REVIEW_PATH) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    key = r.get("turn_id") or r.get("record_key", "")
                    reviewed.add(key)
                except json.JSONDecodeError:
                    continue
    return reviewed


def save_decision(record: dict, verdict: str, reviewer_note: str):
    REVIEW_PATH.parent.mkdir(exist_ok=True)
    key = f"{record['thread_id']}_{record['timestamp']}"
    entry = {
        "turn_id":       key,
        "record_key":    key,
        "thread_id":     record["thread_id"],
        "timestamp":     record["timestamp"],
        "user_query":    record["user_query"],
        "verdict":       verdict,
        "reviewer_note": reviewer_note,
        "reviewed_at":   datetime.now(timezone.utc).isoformat(),
    }
    with open(REVIEW_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ── Page ──────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="cw-navbar">
  <span style="font-size:1.3rem;margin-right:6px">⚠</span>
  <span class="cw-navbar-brand">Cloudway</span>
  <span class="cw-navbar-sep">·</span>
  <span class="cw-navbar-subtitle">Human Review Dashboard — escalated cases requiring verification</span>
  <a class="cw-navbar-link" href="http://localhost:8501" target="_self">← Policy Assistant</a>
</div>
""", unsafe_allow_html=True)

escalated  = load_escalated()
reviewed   = load_reviewed_keys()
pending    = [r for r in escalated
              if f"{r['thread_id']}_{r['timestamp']}" not in reviewed]
n_reviewed = len(escalated) - len(pending)

# ── Metrics ───────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
c1.metric("Total Escalated", len(escalated))
c2.metric("Pending Review",  len(pending))
c3.metric("Reviewed",        n_reviewed)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
st.divider()

if not escalated:
    st.info("No escalated cases yet. Run the pipeline to generate some.")
    st.stop()

tab1, tab2 = st.tabs([f"⏳  Pending  ({len(pending)})",
                       f"✅  Reviewed  ({n_reviewed})"])

# ── Pending tab ───────────────────────────────────────────────────────────────

with tab1:
    if not pending:
        st.success("All escalated cases have been reviewed. ✓")
    else:
        st.caption(f"{len(pending)} case{'s' if len(pending) != 1 else ''} awaiting review")

    for record in reversed(pending):
        key   = f"{record['thread_id']}_{record['timestamp']}"
        ts    = record.get("timestamp", "")[:19].replace("T", " ") + " UTC"
        viol  = record.get("violations", [])
        facts = record.get("extracted_facts", [])
        docs  = record.get("retrieved_docs", [])

        # Prose answer — strip CLAIM/REFUSAL lines
        prose = "\n".join(
            ln for ln in record.get("llm_answer", "").splitlines()
            if not ln.strip().startswith(("CLAIM:", "REFUSAL:"))
        ).strip() or record.get("llm_answer", "")

        # ── Card: use st.container(border=True) — native Streamlit wrapper ──
        with st.container(border=True):

            # Query + metadata + violations row
            q_col, v_col = st.columns([3, 1])
            with q_col:
                st.markdown(
                    f'<p class="cw-case-query">{record["user_query"]}</p>'
                    f'<p class="cw-case-meta">{record.get("thread_id","")} &nbsp;·&nbsp;'
                    f' {ts} &nbsp;·&nbsp; {record.get("latency_ms","?")} ms</p>',
                    unsafe_allow_html=True,
                )
            with v_col:
                if viol:
                    for v in viol:
                        st.markdown(
                            f'<span class="cw-badge cw-badge-violation">⚠ {v}</span>',
                            unsafe_allow_html=True,
                        )

            # LLM answer block
            st.markdown(
                f'<p class="cw-field-label">LLM Answer</p>'
                f'<div class="cw-answer-box">{prose}</div>',
                unsafe_allow_html=True,
            )

            # Extracted facts
            if facts:
                fact_html = " ".join(
                    f'<span class="cw-badge cw-badge-fact">{f}</span>'
                    for f in facts
                )
                st.markdown(
                    f'<p class="cw-field-label">Extracted Facts</p>{fact_html}',
                    unsafe_allow_html=True,
                )

            # Retrieved policy chunks (collapsed)
            if docs:
                with st.expander(f"📄 Retrieved policy chunks ({len(docs)})", expanded=False):
                    for i, doc in enumerate(docs, 1):
                        snippet = doc[:230].replace("\n", " ").strip()
                        st.markdown(
                            f'<p class="cw-field-label">Chunk {i}</p>'
                            f'<p class="cw-chunk-text">{snippet}{"…" if len(doc) > 230 else ""}</p>',
                            unsafe_allow_html=True,
                        )

            st.divider()

            # Review form — native widgets so state management works
            note = st.text_input(
                "Reviewer note",
                key=f"note_{key}",
                placeholder="Optional — explain your decision…",
                label_visibility="collapsed",
            )
            btn_a, btn_r, _ = st.columns([1, 1, 2])
            if btn_a.button("✓  Approve", key=f"approve_{key}",
                            type="primary", use_container_width=True):
                save_decision(record, "approved", note)
                st.rerun()
            if btn_r.button("✕  Reject", key=f"reject_{key}",
                            use_container_width=True):
                save_decision(record, "rejected", note)
                st.rerun()


# ── Reviewed tab ──────────────────────────────────────────────────────────────

with tab2:
    if not REVIEW_PATH.exists():
        st.info("No review decisions recorded yet.")
    else:
        decisions = []
        with open(REVIEW_PATH) as f:
            for line in f:
                try:
                    decisions.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        if not decisions:
            st.info("No review decisions recorded yet.")
        else:
            for d in reversed(decisions):
                is_approved = d["verdict"] == "approved"
                bg    = "#F0FDF4" if is_approved else "#FFF1F2"
                color = "#15803D" if is_approved else "#BE123C"
                icon  = "✓" if is_approved else "✕"
                ts    = d.get("reviewed_at", "")[:16].replace("T", " ") + " UTC"
                note  = d.get("reviewer_note") or ""

                st.markdown(
                    f'<div class="cw-reviewed-row" style="background:{bg}">'
                    f'  <span style="font-size:0.85rem;font-weight:700;color:{color}">{icon}</span>'
                    f'  <span class="cw-reviewed-query">{d["user_query"][:80]}</span>'
                    f'  <span class="cw-reviewed-ts">{ts}</span>'
                    f'</div>'
                    + (f'<p class="cw-reviewed-note">{note}</p>' if note else ""),
                    unsafe_allow_html=True,
                )
