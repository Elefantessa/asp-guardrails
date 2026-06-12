"""
CLI entry point — the external loop pattern.

Each graph.invoke() runs START → END in one shot.
LangGraph checkpoints the state after each run.
The WHILE loop in this file IS the conversation loop — not the graph.

Run:
    source .venv/bin/activate
    python -m src.main

Commands during chat:
    quit   — exit
    reset  — start a new session (new thread_id)
"""

import os
import time

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from src.graph import build_graph
from src.persistence.audit_log import log_turn
from src.telemetry import TRACER

load_dotenv()


def main():
    graph = build_graph()
    session_num = 1
    config = {"configurable": {"thread_id": f"session-{session_num:03d}"}}

    print("=" * 68)
    print("  Cloudway — Holiday Policy Assistant")
    print("  Multi-Agent Guardrails (RAG + ASP Validation)")
    print("=" * 68)
    print("  Type 'quit' to exit, 'reset' for a new session.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            break
        if user_input.lower() == "reset":
            session_num += 1
            config = {"configurable": {"thread_id": f"session-{session_num:03d}"}}
            print(f"  [New session: session-{session_num:03d}]\n")
            continue

        t0 = time.time()
        with TRACER.start_as_current_span("graph.run") as span:
            span.set_attribute("session.thread_id", config["configurable"]["thread_id"])
            span.set_attribute("user.input_length", len(user_input))
            result = graph.invoke(
                {"messages": [HumanMessage(content=user_input)]},
                config=config,
            )
            decision = result.get("decision", "error")
            span.set_attribute("graph.decision", decision)
        latency_ms = int((time.time() - t0) * 1000)

        # ── Audit log every turn ──────────────────────────────────────────────
        ai_msgs_all = [m for m in result["messages"] if hasattr(m, "type") and m.type == "ai"]
        log_turn(
            thread_id=config["configurable"]["thread_id"],
            user_query=user_input,
            llm_answer=ai_msgs_all[-1].content if ai_msgs_all else "",
            extracted_facts=result.get("extracted_facts", []),
            violations=result.get("violations", []),
            decision=decision,
            latency_ms=latency_ms,
            retrieved_docs=result.get("retrieved_docs", []),
        )

        # ── Display assistant response ────────────────────────────────────────
        ai_msgs = [m for m in result["messages"] if hasattr(m, "type") and m.type == "ai"]
        if ai_msgs:
            print(f"\nAssistant: {ai_msgs[-1].content}\n")

        # ── Display decision badge ────────────────────────────────────────────
        if decision == "approved":
            n = len(result.get("derived_facts", []))
            print(f"  [✓ Validated — {n} ASP facts derived]")
        elif decision == "escalated":
            v = result.get("violations", [])
            print(f"  [⚠ ESCALATED — {len(v)} violation(s)]")
            for item in v[:3]:
                print(f"    • {item}")
        elif decision == "pending_info":
            print("  [… waiting for more information]")
        elif decision == "refused_out_of_scope":
            print("  [↷ Out of policy scope — not answered]")
        else:
            print(f"  [? {decision}]")
        print()


if __name__ == "__main__":
    main()
