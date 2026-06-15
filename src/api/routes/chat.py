"""
Chat routes.

POST /api/chat          — send a query, get a guardrailed response
GET  /api/chat/examples — static example queries for the UI sidebar
"""

from __future__ import annotations

import os
import time
import uuid

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage

from src.api.models import ChatRequest, ChatResponse, ExampleQuery
from src.graph import build_graph
from src.persistence.audit_log import log_turn

router = APIRouter(prefix="/api/chat", tags=["chat"])

# ── Graph singleton ───────────────────────────────────────────────────────────

_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


# ── Example queries (static — for the sidebar) ────────────────────────────────

_EXAMPLES: list[ExampleQuery] = [
    ExampleQuery(id="ex01", category="Identity",
                 query="Can John (age 35) make a booking?"),
    ExampleQuery(id="ex02", category="Identity",
                 query="Can Sarah (age 16) make a booking?"),
    ExampleQuery(id="ex03", category="Cancellation",
                 query="What percentage will we lose if we cancel 31 days before departure?"),
    ExampleQuery(id="ex04", category="Cancellation",
                 query="We need to cancel 65 days before. What is the fee?"),
    ExampleQuery(id="ex05", category="Amendment",
                 query="How much does a name change cost?"),
    ExampleQuery(id="ex06", category="Amendment",
                 query="Can I change my accommodation 20 days before departure?"),
    ExampleQuery(id="ex07", category="Payment",
                 query="I booked 100 days before departure. Do I need to pay the full amount now?"),
    ExampleQuery(id="ex08", category="Complaint",
                 query="Can I complain 35 days after returning from holiday?"),
    ExampleQuery(id="ex09", category="Financial Protection",
                 query="Is my holiday financially protected if TUI goes bust?"),
    ExampleQuery(id="ex10", category="Out of scope",
                 query="What is the weather like in Cancun in July?"),
]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/examples", response_model=list[ExampleQuery])
def get_examples() -> list[ExampleQuery]:
    return _EXAMPLES


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    thread_id = req.thread_id or str(uuid.uuid4())
    graph     = _get_graph()
    config    = {"configurable": {"thread_id": thread_id}}

    t0 = time.time()
    try:
        result = graph.invoke(
            {"messages": [HumanMessage(content=req.query)]},
            config=config,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    latency_ms = int((time.time() - t0) * 1000)

    ai_msgs = [m for m in result["messages"] if hasattr(m, "type") and m.type == "ai"]
    answer  = ai_msgs[-1].content if ai_msgs else ""

    extracted_facts      = result.get("extracted_facts", [])
    violations           = result.get("violations", [])
    decision             = result.get("decision", "error")
    retrieved_docs       = result.get("retrieved_docs", [])
    retrieval_scores     = result.get("retrieval_scores", [])
    rewritten_query      = result.get("rewritten_query")
    retrieval_fallback   = result.get("retrieval_fallback_used", False)
    partial_validation   = result.get("partial_validation", False)
    unextractable_claims = result.get("unextractable_claims", [])

    log_turn(
        thread_id=thread_id,
        user_query=req.query,
        llm_answer=answer,
        extracted_facts=extracted_facts,
        violations=violations,
        decision=decision,
        latency_ms=latency_ms,
        retrieved_docs=retrieved_docs,
    )

    return ChatResponse(
        thread_id=thread_id,
        decision=decision,
        answer=answer,
        rewritten_query=rewritten_query,
        retrieval_fallback_used=retrieval_fallback,
        partial_validation=partial_validation,
        extracted_facts=extracted_facts,
        unextractable_claims=unextractable_claims,
        violations=violations,
        retrieved_docs=[d[:400] for d in retrieved_docs],
        retrieval_scores=retrieval_scores,
        latency_ms=latency_ms,
    )
