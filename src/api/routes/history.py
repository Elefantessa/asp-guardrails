"""
Conversation history routes.

GET /api/history/{thread_id} — all turns for a session
GET /api/history             — recent turns across all sessions
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from src.api.models import HistoryTurn
from src.persistence.audit_log import query_logs

router = APIRouter(prefix="/api/history", tags=["history"])


def _record_to_turn(r: dict) -> HistoryTurn:
    turn_id = f"{r['thread_id']}_{r['timestamp']}"
    return HistoryTurn(
        turn_id=turn_id,
        thread_id=r.get("thread_id", ""),
        timestamp=r.get("timestamp", ""),
        user_query=r.get("user_query", ""),
        answer=r.get("llm_answer", ""),
        extracted_facts=r.get("extracted_facts", []),
        violations=r.get("violations", []),
        decision=r.get("decision", ""),
        latency_ms=r.get("latency_ms", 0),
    )


@router.get("", response_model=list[HistoryTurn])
def get_recent_history(limit: int = Query(default=50, le=200)) -> list[HistoryTurn]:
    records = query_logs(thread_id=None, limit=limit)
    return [_record_to_turn(r) for r in reversed(records)]


@router.get("/{thread_id}", response_model=list[HistoryTurn])
def get_thread_history(thread_id: str) -> list[HistoryTurn]:
    records = query_logs(thread_id=thread_id)
    return [_record_to_turn(r) for r in records]
