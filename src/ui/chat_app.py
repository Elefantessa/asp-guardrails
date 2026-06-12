"""
Cloudway — Streamlit Chat Demo

Run:
    streamlit run src/ui/chat_app.py

Shows the full RAG+ASP pipeline with:
  - Live chat interface
  - Decision badge (approved / escalated / pending_info / refused_out_of_scope)
  - ASP facts derived and violations
  - Per-turn latency
  - Session management
"""

import os, sys, time, logging, warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Suppress harmless Streamlit/PyTorch file-watcher noise
logging.getLogger("streamlit.watcher.local_sources_watcher").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=UserWarning, module="torch")
warnings.filterwarnings("ignore", ".*allowed_objects.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", ".*Chroma.*deprecated.*", category=DeprecationWarning)

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

load_dotenv()
for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
    os.environ.pop(k, None)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Cloudway — Policy Assistant",
    page_icon="🛡️",
    layout="wide",
)

# ── Styles ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.decision-approved   { background:#d4edda; border-left:4px solid #28a745; padding:8px 12px; border-radius:4px; }
.decision-escalated  { background:#f8d7da; border-left:4px solid #dc3545; padding:8px 12px; border-radius:4px; }
.decision-pending    { background:#fff3cd; border-left:4px solid #ffc107; padding:8px 12px; border-radius:4px; }
.decision-refused    { background:#e2e3e5; border-left:4px solid #6c757d; padding:8px 12px; border-radius:4px; }
.fact-pill { display:inline-block; background:#e8f4f8; border:1px solid #b8daff;
             border-radius:3px; padding:1px 6px; font-family:monospace; font-size:0.78em; margin:2px; }
.violation-pill { display:inline-block; background:#fdecea; border:1px solid #f5c6cb;
                  border-radius:3px; padding:1px 6px; font-family:monospace; font-size:0.78em; margin:2px; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────

def _init_session():
    if "graph" not in st.session_state:
        import src.agents.rag_agent as _ra
        import src.agents.fact_extractor as _fe
        _ra._llm = None; _ra._retriever = None; _fe._llm = None
        from src.graph import build_graph
        st.session_state.graph = build_graph()
        st.session_state.session_num = 1
        st.session_state.turns = []          # list of turn dicts for display
        st.session_state.thread_id = "ui-session-001"

_init_session()


def _new_session():
    st.session_state.session_num += 1
    n = st.session_state.session_num
    st.session_state.thread_id = f"ui-session-{n:03d}"
    st.session_state.turns = []


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/1/15/Coat_of_arms_of_TUI_Group.svg/200px-Coat_of_arms_of_TUI_Group.svg.png", width=60)
    st.title("Cloudway")
    st.caption("Neuro-Symbolic Policy Compliance")
    st.divider()

    st.subheader("Session")
    st.caption(f"Thread: `{st.session_state.thread_id}`")
    if st.button("🔄 New session", use_container_width=True):
        _new_session()
        st.rerun()

    st.divider()
    st.subheader("Try these")
    examples = [
        "What is the cancellation fee?",
        "What is the cancellation fee if I cancel 65 days before departure?",
        "Must the lead name be an adult to book a holiday?",
        "Can I change my accommodation 20 days before departure?",
        "Is there travel insurance included?",
        "What is the weather like in Mallorca?",
    ]
    for i, ex in enumerate(examples):
        if st.button(ex[:45] + ("…" if len(ex) > 45 else ""), use_container_width=True, key=f"ex_{i}"):
            st.session_state["_prefill"] = ex
            st.rerun()

    st.divider()
    st.caption("🔗 [Human Review](http://localhost:8502)")
    st.caption("📊 [Grafana Traces](http://localhost:3000)")


# ── Display helpers (must be defined before use) ─────────────────────────────

def _clean_answer(raw: str) -> str:
    """
    Return display-ready answer text:
    - Prose lines shown as-is.
    - CLAIM: content appended after prose (stripped of marker).
    - REFUSAL: lines removed entirely.
    """
    lines = raw.splitlines()
    prose, claims = [], []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("CLAIM:"):
            claims.append(stripped[len("CLAIM:"):].strip())
        elif stripped.startswith("REFUSAL:"):
            continue
        else:
            prose.append(line)

    prose_text  = "\n".join(prose).strip()
    claims_text = "\n".join(f"• {c}" for c in claims)

    if prose_text and claims_text:
        return f"{prose_text}\n\n{claims_text}"
    return prose_text or claims_text or raw

def _render_decision_badge(turn: dict):
    decision   = turn["decision"]
    latency    = turn["latency_ms"]
    facts      = turn.get("extracted_facts", [])
    violations = turn.get("violations", [])

    if decision == "approved":
        n_checked = len(facts)
        unverifiable = any("unverifiable" in d for d in turn.get("derived_facts", []))

        if unverifiable:
            st.markdown(
                f'<div class="decision-approved">✅ <b>Approved</b> '
                f'— informational answer (outside ASP coverage) &nbsp;·&nbsp; {latency} ms</div>',
                unsafe_allow_html=True,
            )
            st.caption("ℹ️ This answer contains qualitative claims that cannot be formally verified by ASP. No violations detected.")
        else:
            label = f"{n_checked} fact{'s' if n_checked != 1 else ''} checked" if n_checked else "no numeric claims"
            st.markdown(
                f'<div class="decision-approved">✅ <b>Validated by ASP</b> '
                f'— {label} &nbsp;·&nbsp; {latency} ms</div>',
                unsafe_allow_html=True,
            )
        if facts:
            with st.expander("ASP facts checked", expanded=False):
                for f in facts:
                    st.markdown(f'<span class="fact-pill">{f}</span>', unsafe_allow_html=True)
        _render_retrieved_docs(turn)

    elif decision == "escalated":
        st.markdown(
            f'<div class="decision-escalated">⚠️ <b>ESCALATED — Human review required</b> '
            f'&nbsp;·&nbsp; {latency} ms</div>',
            unsafe_allow_html=True,
        )
        if violations:
            with st.expander(f"Violations ({len(violations)})", expanded=True):
                for v in violations:
                    st.markdown(f'<span class="violation-pill">{v}</span>', unsafe_allow_html=True)

    elif decision == "pending_info":
        st.markdown(
            f'<div class="decision-pending">💬 <b>Awaiting clarification</b> '
            f'&nbsp;·&nbsp; {latency} ms</div>',
            unsafe_allow_html=True,
        )

    elif decision == "refused_out_of_scope":
        st.markdown(
            f'<div class="decision-refused">↷ <b>Out of policy scope</b> '
            f'&nbsp;·&nbsp; {latency} ms</div>',
            unsafe_allow_html=True,
        )


def _render_retrieved_docs(turn: dict):
    docs = turn.get("retrieved_docs", [])
    if not docs:
        return
    with st.expander(f"📄 Retrieved policy chunks ({len(docs)})", expanded=False):
        for i, doc in enumerate(docs, 1):
            snippet = doc[:250].replace("\n", " ").strip()
            st.caption(f"**Chunk {i}:** {snippet}{'…' if len(doc) > 250 else ''}")


# ── Main area ─────────────────────────────────────────────────────────────────

st.title("🛡️ Holiday Policy Assistant")
st.caption("Answers grounded in TUI Terms & Conditions · Validated by ASP (Clingo)")

# Render chat history
for turn in st.session_state.turns:
    with st.chat_message("user"):
        st.write(turn["query"])
    with st.chat_message("assistant"):
        st.write(_clean_answer(turn["answer"]))
        _render_decision_badge(turn)


# ── Input ─────────────────────────────────────────────────────────────────────

prefill = st.session_state.pop("_prefill", "")
user_input = st.chat_input("Ask about the holiday policy…", key="chat_input")

if not user_input and prefill:
    user_input = prefill

def _is_expired_token(exc: Exception) -> bool:
    return "ExpiredToken" in type(exc).__name__ or "ExpiredToken" in str(exc)


def _reset_agents():
    """Reset boto3 singletons so the next call picks up fresh credentials."""
    import src.agents.rag_agent as _ra
    import src.agents.fact_extractor as _fe
    _ra._llm = None
    _ra._retriever = None
    _fe._llm = None
    # Also rebuild the graph to get fresh clients
    from src.graph import build_graph
    st.session_state.graph = build_graph()


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
                        "⏰ **AWS credentials expired.**\n\n"
                        "Please refresh `~/.aws/credentials` then resend your message.",
                        icon="🔑",
                    )
                else:
                    st.error(f"Pipeline error: {type(exc).__name__}: {str(exc)[:200]}")
                st.stop()

        ai_msgs = [m for m in result["messages"] if hasattr(m, "type") and m.type == "ai"]
        answer  = ai_msgs[-1].content if ai_msgs else ""
        st.write(_clean_answer(answer))

        turn = {
            "query": user_input,
            "answer": answer,
            "decision": result.get("decision", "error"),
            "latency_ms": latency_ms,
            "extracted_facts": result.get("extracted_facts", []),
            "violations": result.get("violations", []),
            "derived_facts": result.get("derived_facts", []),
            "retrieved_docs": result.get("retrieved_docs", []),
        }
        _render_decision_badge(turn)

        log_turn(
            thread_id=st.session_state.thread_id,
            user_query=user_input,
            llm_answer=answer,
            extracted_facts=turn["extracted_facts"],
            violations=turn["violations"],
            decision=turn["decision"],
            latency_ms=latency_ms,
            retrieved_docs=turn["retrieved_docs"],
        )

    st.session_state.turns.append(turn)
    st.rerun()
