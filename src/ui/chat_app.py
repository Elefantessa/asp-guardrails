"""
Cloudway — Policy Assistant (Corporate UI)

Run:
    streamlit run src/ui/chat_app.py
"""

import os, sys, time, logging, warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

logging.getLogger("streamlit.watcher.local_sources_watcher").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=UserWarning, module="torch")
warnings.filterwarnings("ignore", ".*allowed_objects.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", ".*Chroma.*deprecated.*", category=DeprecationWarning)

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

load_dotenv()
for _k in list(os.environ.keys()):
    if _k.startswith(("aws_", "bedrock_")):
        os.environ.setdefault(_k.upper(), os.environ[_k])

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Cloudway · Policy Assistant",
    page_icon="🛡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Corporate CSS — overrides Streamlit defaults completely ───────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ── Reset & base ── */
*, html, body { box-sizing: border-box; }
html, body, [class*="css"], .stApp {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    background-color: #F8FAFC !important;
}

/* ── Hide Streamlit chrome ── */
#MainMenu, header[data-testid="stHeader"], footer,
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"] { display: none !important; visibility: hidden !important; }

/* ── Main content area ── */
.main .block-container {
    padding: 1.5rem 2rem 2rem !important;
    max-width: 1100px !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #FFFFFF !important;
    border-right: 1px solid #E2E8F0 !important;
}
[data-testid="stSidebar"] .block-container {
    padding: 1.2rem 1rem !important;
}
[data-testid="stSidebar"] hr {
    border-color: #E2E8F0 !important;
    margin: 0.8rem 0 !important;
}
[data-testid="stSidebar"] h2 {
    font-size: 1rem !important;
    font-weight: 700 !important;
    color: #0F172A !important;
    margin-bottom: 0.1rem !important;
}
[data-testid="stSidebar"] p, [data-testid="stSidebar"] small {
    font-size: 0.78rem !important;
    color: #64748B !important;
}

/* ── Sidebar buttons (example queries) ── */
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
    background: #F8FAFC !important;
    border: 1px solid #E2E8F0 !important;
    color: #334155 !important;
    font-size: 0.76rem !important;
    padding: 6px 10px !important;
    border-radius: 6px !important;
    text-align: left !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 400 !important;
}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {
    background: #EFF6FF !important;
    border-color: #BFDBFE !important;
    color: #1D4ED8 !important;
}

/* ── New-session button ── */
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
    background: #1D4ED8 !important;
    color: white !important;
    border: none !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    border-radius: 6px !important;
    padding: 7px 14px !important;
}
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"]:hover {
    background: #1E40AF !important;
}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    padding: 0.4rem 0 !important;
}
[data-testid="stChatMessageContent"] p {
    font-size: 0.88rem !important;
    line-height: 1.6 !important;
    color: #1E293B !important;
}

/* User bubble */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
    background: #1D4ED8 !important;
    color: white !important;
    border-radius: 16px 16px 4px 16px !important;
    padding: 10px 16px !important;
    max-width: 72% !important;
    margin-left: auto !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] p {
    color: white !important;
}

/* Assistant bubble */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stChatMessageContent"] {
    background: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 4px 16px 16px 16px !important;
    padding: 12px 16px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
}

/* ── Spinner ── */
[data-testid="stSpinner"] p { font-size: 0.83rem !important; color: #64748B !important; }

/* ── Chat input bar ── */
[data-testid="stChatInput"] {
    border: 1.5px solid #E2E8F0 !important;
    border-radius: 10px !important;
    background: #FFFFFF !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;
}
[data-testid="stChatInput"]:focus-within {
    border-color: #1D4ED8 !important;
    box-shadow: 0 0 0 3px rgba(29,78,216,0.12) !important;
}
[data-testid="stChatInput"] textarea {
    font-size: 0.88rem !important;
    color: #0F172A !important;
}
[data-testid="stChatInputSubmitButton"] svg { color: #1D4ED8 !important; }

/* ── Expanders ── */
[data-testid="stExpander"] {
    border: 1px solid #E2E8F0 !important;
    border-radius: 8px !important;
    background: #FFFFFF !important;
    margin: 6px 0 !important;
}
[data-testid="stExpander"] summary {
    font-size: 0.80rem !important;
    font-weight: 500 !important;
    color: #475569 !important;
    padding: 8px 12px !important;
}

/* ── Code blocks ── */
.stCode, [data-testid="stCode"] {
    font-size: 0.75rem !important;
    border-radius: 6px !important;
    background: #F1F5F9 !important;
    border: 1px solid #E2E8F0 !important;
    padding: 4px 10px !important;
}

/* ── Section labels ── */
.cw-section-label {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: #94A3B8;
    margin: 14px 0 6px;
}

/* ── Top navbar ── */
.cw-navbar {
    display: flex;
    align-items: center;
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 12px 20px;
    margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.cw-navbar-brand {
    font-size: 1.05rem;
    font-weight: 700;
    color: #0F172A;
    letter-spacing: -0.02em;
}
.cw-navbar-sep {
    color: #CBD5E1;
    margin: 0 8px;
    font-size: 1.1rem;
}
.cw-navbar-subtitle {
    font-size: 0.78rem;
    color: #64748B;
    font-weight: 400;
}
.cw-navbar-link {
    margin-left: auto;
    font-size: 0.78rem;
    color: #1D4ED8;
    text-decoration: none;
    font-weight: 500;
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-radius: 6px;
    padding: 4px 12px;
}
.cw-navbar-link:hover { background: #DBEAFE; }

/* ── Decision cards ── */
.cw-decision {
    display: flex;
    align-items: center;
    gap: 10px;
    border-radius: 8px;
    padding: 9px 14px;
    margin: 10px 0 6px;
    font-size: 0.82rem;
    font-weight: 600;
}
.cw-decision-label { flex: 1; }
.cw-decision-meta  { font-size: 0.72rem; font-weight: 400; opacity: 0.7; }

.cw-approved  { background: #F0FDF4; border-left: 4px solid #22C55E; color: #15803D; }
.cw-escalated { background: #FFF1F2; border-left: 4px solid #F43F5E; color: #BE123C; }
.cw-pending   { background: #FFFBEB; border-left: 4px solid #F59E0B; color: #B45309; }
.cw-refused   { background: #F8FAFC; border-left: 4px solid #94A3B8; color: #475569; }

/* ── Inline badges ── */
.cw-badge {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 0.70rem;
    font-weight: 500;
    border: 1px solid;
    margin: 2px 2px 2px 0;
    font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
    white-space: nowrap;
}
.cw-badge-fact     { background:#EFF6FF; border-color:#BFDBFE; color:#1D4ED8; }
.cw-badge-violation{ background:#FFF1F2; border-color:#FECDD3; color:#BE123C; }
.cw-badge-unmapped { background:#FFFBEB; border-color:#FDE68A; color:#92400E; }
.cw-badge-rewrite  { background:#F5F3FF; border-color:#DDD6FE; color:#6D28D9; }
.cw-badge-warning  { background:#FFFBEB; border-color:#FDE68A; color:#92400E; font-family:sans-serif; }

/* ── Score bar ── */
.cw-score-wrap { margin: 5px 0; }
.cw-score-label { font-size: 0.68rem; color: #94A3B8; margin-bottom: 3px; display:flex; justify-content:space-between; }
.cw-score-track { height: 4px; border-radius: 2px; background: #E2E8F0; }
.cw-score-fill  { height: 4px; border-radius: 2px; transition: width 0.3s ease; }
.cw-chunk-text  { font-size: 0.75rem; color: #64748B; margin: 3px 0 10px; line-height: 1.4; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────

def _init_session():
    if "graph" not in st.session_state:
        import src.agents.rag_agent as _ra
        import src.agents.fact_extractor as _fe
        _ra._llm = None
        _ra._vectorstore = None
        _fe._llm = None
        from src.graph import build_graph
        st.session_state.graph       = build_graph()
        st.session_state.session_num = 1
        st.session_state.turns       = []
        st.session_state.thread_id   = "ui-session-001"

_init_session()


def _new_session():
    st.session_state.session_num += 1
    n = st.session_state.session_num
    st.session_state.thread_id = f"ui-session-{n:03d}"
    st.session_state.turns = []


def _reset_agents():
    import src.agents.rag_agent as _ra
    import src.agents.fact_extractor as _fe
    _ra._llm = None
    _ra._vectorstore = None
    _fe._llm = None
    from src.graph import build_graph
    st.session_state.graph = build_graph()


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🛡 Cloudway")
    st.caption("Neuro-Symbolic Policy Compliance")
    st.divider()

    st.markdown('<p class="cw-section-label">Current Session</p>', unsafe_allow_html=True)
    st.code(st.session_state.thread_id, language=None)
    if st.button("↺  New Session", use_container_width=True, type="primary"):
        _new_session()
        st.rerun()

    st.divider()
    st.markdown('<p class="cw-section-label">Example Queries</p>', unsafe_allow_html=True)

    _EXAMPLES = {
        "Identity & Eligibility": [
            "Can John (age 35) make a booking?",
            "Can Sarah (age 16) make a booking?",
            "Emma (age 15) is travelling with adult guardian Mark. Can she book?",
        ],
        "Cancellation Fees": [
            "What percentage will we lose if we cancel 31 days before?",
            "We need to cancel 65 days before. What is the fee?",
        ],
        "Amendment Fees": [
            "How much does a name change cost?",
            "Can I change my accommodation 20 days before departure?",
        ],
        "Payment & Complaints": [
            "I booked 100 days before. Do I need to pay in full now?",
            "I complained 35 days after returning — is that within deadline?",
        ],
        "Out of Scope": [
            "What is the weather like in Mallorca?",
            "Is travel insurance included?",
        ],
    }

    for category, queries in _EXAMPLES.items():
        with st.expander(category, expanded=False):
            for q in queries:
                label = q[:50] + "…" if len(q) > 50 else q
                if st.button(label, use_container_width=True, key=f"ex_{hash(q)}"):
                    st.session_state["_prefill"] = q
                    st.rerun()

    st.divider()
    st.markdown(
        '🔍 <a href="http://localhost:8502" style="color:#1D4ED8;font-size:0.8rem;text-decoration:none;font-weight:500">'
        'Human Review Dashboard</a>',
        unsafe_allow_html=True,
    )


# ── Display helpers ───────────────────────────────────────────────────────────

import json as _json
from pathlib import Path as _Path
from datetime import datetime as _datetime, timezone as _tz

_REVIEW_PATH = _Path("logs/review_decisions.jsonl")

_ESCALATED_HOLDING = (
    "Thank you for your question. Our compliance team is reviewing this query "
    "to ensure the answer fully aligns with our policy. "
    "We will follow up with a verified response shortly."
)


def _clean_answer(raw: str) -> str:
    lines = raw.splitlines()
    prose = [ln for ln in lines if not ln.strip().startswith(("CLAIM:", "REFUSAL:"))]
    return "\n".join(prose).strip() or raw


@st.cache_data(ttl=5)
def _load_review_decisions() -> dict[str, str]:
    """
    Return {turn_key: verdict} from review_decisions.jsonl.
    Cached for 5 seconds so the chat UI picks up approvals quickly
    without hitting disk on every widget interaction.
    """
    decisions: dict[str, str] = {}
    if not _REVIEW_PATH.exists():
        return decisions
    with open(_REVIEW_PATH) as f:
        for line in f:
            try:
                r = _json.loads(line)
                key = r.get("turn_id") or r.get("record_key", "")
                if key:
                    decisions[key] = r.get("verdict", "")
            except _json.JSONDecodeError:
                continue
    return decisions


def _display_answer(answer: str, decision: str, turn_key: str = "") -> None:
    """
    Show the answer to the client — with three states for escalated turns:

      1. Still pending review  → amber holding message
      2. Approved by reviewer  → full answer + green "Verified" banner
      3. Rejected by reviewer  → neutral message (answer withheld)

    For all other decisions the answer is displayed immediately.
    """
    if decision != "escalated":
        st.write(_clean_answer(answer))
        return

    if turn_key:
        verdict = _load_review_decisions().get(turn_key, "")
    else:
        verdict = ""

    if verdict == "approved":
        st.markdown(
            '<div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;'
            'padding:8px 14px;font-size:0.78rem;font-weight:600;color:#15803D;margin-bottom:8px">'
            '✓ Verified by compliance team — answer released</div>',
            unsafe_allow_html=True,
        )
        st.write(_clean_answer(answer))
    elif verdict == "rejected":
        st.markdown(
            '<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;'
            'padding:12px 16px;font-size:0.86rem;color:#64748B;line-height:1.55">'
            '✕ Our team reviewed this query and determined that a reliable answer '
            'cannot be provided at this time. Please contact support for assistance.'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:8px;'
            f'padding:12px 16px;font-size:0.86rem;color:#92400E;line-height:1.55">'
            f'⏳ {_ESCALATED_HOLDING}'
            f'</div>',
            unsafe_allow_html=True,
        )


def _score_color(score: float) -> str:
    if score < 0.65:  return "#22C55E"
    if score < 1.10:  return "#F59E0B"
    return "#F43F5E"


def _render_turn(turn: dict):
    decision   = turn["decision"]
    latency    = turn["latency_ms"]
    facts      = turn.get("extracted_facts", [])
    violations = turn.get("violations", [])
    unmapped   = turn.get("unextractable_claims", [])
    rewritten  = turn.get("rewritten_query")
    fallback   = turn.get("retrieval_fallback_used", False)
    partial    = turn.get("partial_validation", False)
    scores     = turn.get("retrieval_scores", [])
    docs       = turn.get("retrieved_docs", [])

    _META = {
        "approved":             ("✓", "Validated by ASP",              "cw-approved"),
        "escalated":            ("⚠", "Escalated — human review needed","cw-escalated"),
        "pending_info":         ("?", "Awaiting clarification",         "cw-pending"),
        "refused_out_of_scope": ("—", "Out of policy scope",            "cw-refused"),
    }
    icon, label, css = _META.get(decision, ("·", decision, "cw-refused"))

    # Extra warning badges
    extra = ""
    if partial:
        extra += '<span class="cw-badge cw-badge-warning">⚠ Partial validation</span> '
    if fallback:
        extra += '<span class="cw-badge cw-badge-warning">⟲ RAG fallback used</span>'

    st.markdown(
        f'<div class="cw-decision {css}">'
        f'  <span style="font-size:1rem">{icon}</span>'
        f'  <span class="cw-decision-label">{label}</span>'
        f'  <span class="cw-decision-meta">{latency} ms</span>'
        f'</div>'
        + (f'<div style="margin:2px 0 6px">{extra}</div>' if extra else ""),
        unsafe_allow_html=True,
    )

    # Violations
    if violations:
        v_html = " ".join(
            f'<span class="cw-badge cw-badge-violation">{v}</span>'
            for v in violations
        )
        st.markdown(
            f'<p style="margin:4px 0 2px;font-size:0.75rem;font-weight:600;color:#BE123C">'
            f'ASP violations</p>{v_html}',
            unsafe_allow_html=True,
        )

    # ASP facts
    if facts or unmapped:
        fact_count = len(facts)
        unmapped_count = len(unmapped)
        label_str = f"{fact_count} fact{'s' if fact_count != 1 else ''} checked"
        if unmapped_count:
            label_str += f" · {unmapped_count} unmapped"

        with st.expander(f"Symbolic reasoning — {label_str}", expanded=(decision == "approved")):
            if facts:
                st.markdown(
                    '<p style="font-size:0.72rem;font-weight:600;color:#64748B;margin-bottom:4px">VERIFIED FACTS</p>'
                    + " ".join(f'<span class="cw-badge cw-badge-fact">{f}</span>' for f in facts),
                    unsafe_allow_html=True,
                )
            if unmapped:
                st.markdown(
                    '<p style="font-size:0.72rem;font-weight:600;color:#92400E;margin:8px 0 4px">UNVALIDATED CLAIMS</p>'
                    + " ".join(f'<span class="cw-badge cw-badge-unmapped">{u}</span>' for u in unmapped),
                    unsafe_allow_html=True,
                )

    # Policy chunks + rewritten query
    if docs or rewritten:
        title = f"Policy sources — {len(docs)} chunk{'s' if len(docs) != 1 else ''}"
        with st.expander(title, expanded=False):
            if rewritten:
                st.markdown(
                    '<p style="font-size:0.72rem;font-weight:600;color:#6D28D9;margin-bottom:6px">REWRITTEN QUERY</p>'
                    + f'<span class="cw-badge cw-badge-rewrite">↳ {rewritten}</span>',
                    unsafe_allow_html=True,
                )
                st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)

            for i, doc in enumerate(docs):
                score    = scores[i] if i < len(scores) else None
                color    = _score_color(score) if score is not None else "#94A3B8"
                fill_pct = max(4, min(100, int((2.2 - (score or 1.1)) / 2.2 * 100)))
                score_str = f"{score:.3f}" if score is not None else "—"
                snippet  = doc[:260].replace("\n", " ").strip()

                st.markdown(
                    f'<div class="cw-score-wrap">'
                    f'  <div class="cw-score-label">'
                    f'    <span>Chunk {i+1}</span>'
                    f'    <span style="color:{color};font-weight:600">score {score_str}</span>'
                    f'  </div>'
                    f'  <div class="cw-score-track">'
                    f'    <div class="cw-score-fill" style="width:{fill_pct}%;background:{color}"></div>'
                    f'  </div>'
                    f'</div>'
                    f'<p class="cw-chunk-text">{snippet}{"…" if len(doc) > 260 else ""}</p>',
                    unsafe_allow_html=True,
                )


# ── Navbar ────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="cw-navbar">
  <span class="cw-navbar-brand">Cloudway</span>
  <span class="cw-navbar-sep">·</span>
  <span class="cw-navbar-subtitle">Holiday Policy Assistant — grounded answers, ASP-validated</span>
  <a class="cw-navbar-link" href="http://localhost:8502" target="_self">Review Dashboard →</a>
</div>
""", unsafe_allow_html=True)


# ── Chat history ──────────────────────────────────────────────────────────────

for turn in st.session_state.turns:
    with st.chat_message("user"):
        st.write(turn["query"])
    with st.chat_message("assistant"):
        _display_answer(turn["answer"], turn["decision"], turn.get("turn_key", ""))
        _render_turn(turn)


# ── Input ─────────────────────────────────────────────────────────────────────

prefill    = st.session_state.pop("_prefill", "")
user_input = st.chat_input("Ask about the holiday policy…")
if not user_input and prefill:
    user_input = prefill


def _is_expired_token(exc: Exception) -> bool:
    return "ExpiredToken" in type(exc).__name__ or "ExpiredToken" in str(exc)


if user_input:
    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Retrieving policy · Generating answer · Validating with ASP…"):
            from src.telemetry import TRACER
            from src.persistence.audit_log import log_turn

            t0 = time.time()
            try:
                with TRACER.start_as_current_span("graph.run") as span:
                    span.set_attribute("session.thread_id", st.session_state.thread_id)
                    result = st.session_state.graph.invoke(
                        {"messages": [HumanMessage(content=user_input)]},
                        config={"configurable": {"thread_id": st.session_state.thread_id}},
                    )
                    span.set_attribute("graph.decision", result.get("decision", "error"))
                latency_ms = int((time.time() - t0) * 1000)
            except Exception as exc:
                if _is_expired_token(exc):
                    _reset_agents()
                    st.error(
                        "⏰ **AWS credentials expired.**  \n"
                        "Please update `.env` and resend your message.",
                        icon="🔑",
                    )
                else:
                    st.error(f"Pipeline error: {type(exc).__name__}: {str(exc)[:200]}")
                st.stop()

        ai_msgs  = [m for m in result["messages"] if hasattr(m, "type") and m.type == "ai"]
        answer   = ai_msgs[-1].content if ai_msgs else ""
        decision = result.get("decision", "error")

        # Log BEFORE display so turn_key is available for _display_answer
        log_ts = log_turn(
            thread_id=st.session_state.thread_id,
            user_query=user_input,
            llm_answer=answer,
            extracted_facts=result.get("extracted_facts", []),
            violations=result.get("violations", []),
            decision=decision,
            latency_ms=latency_ms,
            retrieved_docs=result.get("retrieved_docs", []),
        )
        turn_key = f"{st.session_state.thread_id}_{log_ts}" if log_ts else ""

        _display_answer(answer, decision, turn_key)

        turn = {
            "query":                    user_input,
            "answer":                   answer,
            "decision":                 decision,
            "latency_ms":               latency_ms,
            "turn_key":                 turn_key,
            "extracted_facts":          result.get("extracted_facts", []),
            "violations":               result.get("violations", []),
            "unextractable_claims":     result.get("unextractable_claims", []),
            "derived_facts":            result.get("derived_facts", []),
            "retrieved_docs":           result.get("retrieved_docs", []),
            "retrieval_scores":         result.get("retrieval_scores", []),
            "rewritten_query":          result.get("rewritten_query"),
            "retrieval_fallback_used":  result.get("retrieval_fallback_used", False),
            "partial_validation":       result.get("partial_validation", False),
        }
        _render_turn(turn)

    st.session_state.turns.append(turn)
    st.rerun()
