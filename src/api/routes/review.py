"""
Human review routes.

GET  /api/review/pending        — escalated cases awaiting review
POST /api/review/{turn_id}      — submit approve/reject decision
GET  /api/review/history        — all reviewed cases
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.api.models import ReviewDecision, ReviewHistoryItem, ReviewItem
from src.persistence.audit_log import query_logs

router = APIRouter(prefix="/api/review", tags=["review"])

_REVIEW_PATH = Path(os.getenv("REVIEW_LOG_PATH", "logs/review_decisions.jsonl"))


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_reviewed_ids() -> set[str]:
    reviewed: set[str] = set()
    if _REVIEW_PATH.exists():
        with open(_REVIEW_PATH) as f:
            for line in f:
                try:
                    reviewed.add(json.loads(line).get("turn_id", ""))
                except json.JSONDecodeError:
                    continue
    return reviewed


def _record_to_review_item(r: dict) -> ReviewItem:
    return ReviewItem(
        turn_id=f"{r['thread_id']}_{r['timestamp']}",
        thread_id=r.get("thread_id", ""),
        timestamp=r.get("timestamp", ""),
        user_query=r.get("user_query", ""),
        answer=r.get("llm_answer", ""),
        violations=r.get("violations", []),
        extracted_facts=r.get("extracted_facts", []),
        decision=r.get("decision", ""),
        latency_ms=r.get("latency_ms", 0),
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/pending", response_model=list[ReviewItem])
def get_pending() -> list[ReviewItem]:
    all_records = query_logs(thread_id=None, limit=500)
    reviewed_ids = _load_reviewed_ids()
    pending = [
        r for r in all_records
        if r.get("decision") == "escalated"
        and f"{r['thread_id']}_{r['timestamp']}" not in reviewed_ids
    ]
    return [_record_to_review_item(r) for r in reversed(pending)]


@router.post("/{turn_id}", status_code=200)
def submit_review(turn_id: str, body: ReviewDecision) -> dict:
    all_records = query_logs(thread_id=None, limit=500)
    match = next(
        (r for r in all_records
         if f"{r['thread_id']}_{r['timestamp']}" == turn_id),
        None,
    )
    if match is None:
        raise HTTPException(status_code=404, detail=f"Turn '{turn_id}' not found in audit log.")

    already_reviewed = _load_reviewed_ids()
    if turn_id in already_reviewed:
        raise HTTPException(status_code=409, detail="This turn has already been reviewed.")

    verdict = "approved" if body.approved else "rejected"
    entry = {
        "turn_id":       turn_id,
        "thread_id":     match["thread_id"],
        "timestamp":     match["timestamp"],
        "user_query":    match["user_query"],
        "verdict":       verdict,
        "reviewer_note": body.reviewer_note,
        "reviewed_at":   datetime.now(timezone.utc).isoformat(),
    }
    _REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_REVIEW_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

    return {"turn_id": turn_id, "verdict": verdict}


@router.get("/history", response_model=list[ReviewHistoryItem])
def get_review_history() -> list[ReviewHistoryItem]:
    if not _REVIEW_PATH.exists():
        return []
    items: list[ReviewHistoryItem] = []
    with open(_REVIEW_PATH) as f:
        for line in f:
            try:
                r = json.loads(line)
                items.append(ReviewHistoryItem(
                    turn_id=r.get("turn_id", ""),
                    thread_id=r.get("thread_id", ""),
                    timestamp=r.get("timestamp", ""),
                    user_query=r.get("user_query", ""),
                    verdict=r.get("verdict", ""),
                    reviewer_note=r.get("reviewer_note"),
                    reviewed_at=r.get("reviewed_at", ""),
                ))
            except (json.JSONDecodeError, Exception):
                continue
    return list(reversed(items))
