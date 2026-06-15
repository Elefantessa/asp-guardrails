"""
Cloudway — Conversation History

Accessible at http://localhost:8501/History
Shows all turns from logs/audit.jsonl across all sessions.
"""

import sys, json
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Cloudway · History",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stApp {
    font-family: 'Inter', -apple-system, sans-serif !important;
    background-color: #F8FAFC !important;
}
#MainMenu, header[data-testid="stHeader"], footer,
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"] { display:none !important; visibility:hidden !important; }
.main .block-container { padding:1.5rem 2rem !important; max-width:1100px !important; }

[data-testid="metric-container"] {
    background:#FFFFFF !important; border:1px solid #E2E8F0 !important;
    border-radius:10px !important; padding:14px 18px !important;
    box-shadow:0 1px 3px rgba(0,0,0,.05) !important;
}
[data-testid="metric-container"] label {
    font-size:0.70rem !important; font-weight:700 !important;
    text-transform:uppercase !important; letter-spacing:.06em !important; color:#94A3B8 !important;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-size:1.8rem !important; font-weight:700 !important; color:#0F172A !important;
}

[data-testid="stVerticalBlockBorderWrapper"] {
    border:1px solid #E2E8F0 !important; border-radius:10px !important;
    background:#FFFFFF !important; box-shadow:0 1px 3px rgba(0,0,0,.05) !important;
    margin-bottom:10px !important;
}

[data-testid="stSelectbox"] > div > div {
    border:1.5px solid #E2E8F0 !important; border-radius:7px !important;
    font-size:0.83rem !important;
}
[data-testid="stTextInput"] input {
    border:1.5px solid #E2E8F0 !important; border-radius:7px !important;
    font-size:0.83rem !important;
}

.cw-navbar {
    display:flex; align-items:center;
    background:#FFFFFF; border:1px solid #E2E8F0; border-radius:10px;
    padding:12px 20px; margin-bottom:20px;
    box-shadow:0 1px 3px rgba(0,0,0,.06);
}
.cw-navbar-brand    { font-size:1.05rem; font-weight:700; color:#0F172A; letter-spacing:-.02em; }
.cw-navbar-sep      { color:#CBD5E1; margin:0 8px; }
.cw-navbar-subtitle { font-size:0.78rem; color:#64748B; }
.cw-navbar-link     {
    font-size:0.78rem; color:#1D4ED8; text-decoration:none; font-weight:500;
    background:#EFF6FF; border:1px solid #BFDBFE; border-radius:6px; padding:4px 12px;
}

.cw-badge {
    display:inline-flex; align-items:center;
    border-radius:4px; padding:2px 7px; margin:2px 2px 2px 0;
    font-size:0.68rem; font-weight:500; border:1px solid;
    font-family:'JetBrains Mono','Courier New',monospace; white-space:nowrap;
}
.cw-badge-fact      { background:#EFF6FF; border-color:#BFDBFE; color:#1D4ED8; }
.cw-badge-violation { background:#FFF1F2; border-color:#FECDD3; color:#BE123C; }

.cw-decision-dot {
    display:inline-block; width:8px; height:8px;
    border-radius:50%; margin-right:6px; vertical-align:middle;
}
.cw-q    { font-size:0.88rem; font-weight:600; color:#0F172A; margin:0 0 3px; }
.cw-meta { font-size:0.70rem; color:#94A3B8; margin:0 0 8px; }
.cw-ans  {
    background:#F8FAFC; border:1px solid #E2E8F0; border-radius:7px;
    padding:8px 12px; font-size:0.80rem; color:#475569;
    white-space:pre-wrap; line-height:1.5; margin:4px 0 6px;
}
</style>
""", unsafe_allow_html=True)

AUDIT_PATH   = Path("logs/audit.jsonl")
REVIEW_PATH  = Path("logs/review_decisions.jsonl")

_DECISION_STYLE = {
    "approved":             ("#22C55E", "✓ Approved"),
    "escalated":            ("#F43F5E", "⚠ Escalated"),
    "pending_info":         ("#F59E0B", "? Pending info"),
    "refused_out_of_scope": ("#94A3B8", "— Out of scope"),
}

# ── Load data ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=10)
def _load_all() -> list[dict]:
    if not AUDIT_PATH.exists():
        return []
    records = []
    with open(AUDIT_PATH) as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return list(reversed(records))   # newest first


@st.cache_data(ttl=5)
def _load_verdicts() -> dict[str, str]:
    verdicts: dict[str, str] = {}
    if not REVIEW_PATH.exists():
        return verdicts
    with open(REVIEW_PATH) as f:
        for line in f:
            try:
                r = json.loads(line)
                key = r.get("turn_id") or r.get("record_key", "")
                if key:
                    verdicts[key] = r.get("verdict", "")
            except json.JSONDecodeError:
                continue
    return verdicts


# ── Page ──────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="cw-navbar">
  <span style="font-size:1.2rem;margin-right:6px">📋</span>
  <span class="cw-navbar-brand">Cloudway</span>
  <span class="cw-navbar-sep">·</span>
  <span class="cw-navbar-subtitle">Conversation History — all sessions from audit log</span>
  <div style="margin-left:auto;display:flex;gap:8px">
    <a class="cw-navbar-link" href="http://localhost:8501" target="_self">← Chat</a>
    <a class="cw-navbar-link" href="http://localhost:8502" target="_self">Review →</a>
  </div>
</div>
""", unsafe_allow_html=True)

all_records = _load_all()
verdicts    = _load_verdicts()

if not all_records:
    st.info("No conversation history yet. Start chatting at http://localhost:8501")
    st.stop()

# ── Metrics ───────────────────────────────────────────────────────────────────
counts = Counter(r["decision"] for r in all_records)
threads = len({r["thread_id"] for r in all_records})

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total Turns",   len(all_records))
m2.metric("Sessions",      threads)
m3.metric("Approved",      counts.get("approved", 0))
m4.metric("Escalated",     counts.get("escalated", 0))
m5.metric("Out of scope",  counts.get("refused_out_of_scope", 0))

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ── Filters ───────────────────────────────────────────────────────────────────
fc1, fc2, fc3 = st.columns([2, 2, 1])

all_threads = sorted({r["thread_id"] for r in all_records}, reverse=True)
session_filter = fc1.selectbox(
    "Session", ["All sessions"] + all_threads, label_visibility="collapsed"
)
decision_filter = fc2.selectbox(
    "Decision", ["All decisions", "approved", "escalated", "pending_info", "refused_out_of_scope"],
    label_visibility="collapsed",
)
if fc3.button("↺ Refresh", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# Apply filters
filtered = all_records
if session_filter != "All sessions":
    filtered = [r for r in filtered if r["thread_id"] == session_filter]
if decision_filter != "All decisions":
    filtered = [r for r in filtered if r["decision"] == decision_filter]

st.caption(f"Showing {len(filtered)} of {len(all_records)} turns")
st.divider()

# ── Records ───────────────────────────────────────────────────────────────────
for r in filtered:
    decision = r.get("decision", "")
    dot_color, decision_label = _DECISION_STYLE.get(decision, ("#94A3B8", decision))
    ts = r.get("timestamp", "")[:19].replace("T", " ") + " UTC"

    turn_key  = f"{r['thread_id']}_{r['timestamp']}"
    verdict   = verdicts.get(turn_key, "")

    # Prose answer (no CLAIM/REFUSAL lines)
    prose = "\n".join(
        ln for ln in r.get("llm_answer", "").splitlines()
        if not ln.strip().startswith(("CLAIM:", "REFUSAL:"))
    ).strip() or r.get("llm_answer", "")

    with st.container(border=True):
        # Header row
        h1, h2 = st.columns([4, 1])
        with h1:
            st.markdown(
                f'<p class="cw-q">{r["user_query"]}</p>'
                f'<p class="cw-meta">'
                f'  <span class="cw-decision-dot" style="background:{dot_color}"></span>'
                f'  {decision_label} &nbsp;·&nbsp; {r["thread_id"]} &nbsp;·&nbsp; {ts}'
                f'  &nbsp;·&nbsp; {r.get("latency_ms","?")} ms'
                + (f' &nbsp;·&nbsp; <b style="color:#15803D">✓ Reviewer approved</b>' if verdict == "approved" else "")
                + (f' &nbsp;·&nbsp; <b style="color:#BE123C">✕ Reviewer rejected</b>' if verdict == "rejected" else "")
                + '</p>',
                unsafe_allow_html=True,
            )
        with h2:
            viol = r.get("violations", [])
            if viol:
                for v in viol:
                    st.markdown(
                        f'<span class="cw-badge cw-badge-violation">⚠ {v[:30]}</span>',
                        unsafe_allow_html=True,
                    )

        # Answer (collapsed for escalated-pending, expanded otherwise)
        show_answer = not (decision == "escalated" and not verdict)
        with st.expander(
            "Answer" + (" (withheld — pending review)" if decision == "escalated" and not verdict else ""),
            expanded=show_answer,
        ):
            if decision == "escalated" and not verdict:
                st.caption("This answer was escalated and is awaiting reviewer approval before release.")
            else:
                st.markdown(
                    f'<div class="cw-ans">{prose if prose else "—"}</div>',
                    unsafe_allow_html=True,
                )

        # Facts
        facts = r.get("extracted_facts", [])
        if facts:
            st.markdown(
                " ".join(f'<span class="cw-badge cw-badge-fact">{f}</span>' for f in facts),
                unsafe_allow_html=True,
            )
