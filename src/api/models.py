"""
FastAPI Pydantic models for request / response contracts.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    thread_id: str | None = Field(
        default=None,
        description="Existing session ID. Omit or pass null to start a new session.",
    )


class ChatResponse(BaseModel):
    thread_id: str
    decision: str
    answer: str
    rewritten_query: str | None = None
    retrieval_fallback_used: bool = False
    partial_validation: bool = False
    extracted_facts: list[str] = []
    unextractable_claims: list[str] = []
    violations: list[str] = []
    retrieved_docs: list[str] = []
    retrieval_scores: list[float] = []
    latency_ms: int = 0


class ExampleQuery(BaseModel):
    id: str
    category: str
    query: str


# ── History ───────────────────────────────────────────────────────────────────

class HistoryTurn(BaseModel):
    turn_id: str
    thread_id: str
    timestamp: str
    user_query: str
    answer: str
    extracted_facts: list[str]
    violations: list[str]
    decision: str
    latency_ms: int


# ── Review ────────────────────────────────────────────────────────────────────

class ReviewItem(BaseModel):
    turn_id: str
    thread_id: str
    timestamp: str
    user_query: str
    answer: str
    violations: list[str]
    extracted_facts: list[str]
    decision: str
    latency_ms: int


class ReviewDecision(BaseModel):
    approved: bool
    reviewer_note: str | None = None


class ReviewHistoryItem(BaseModel):
    turn_id: str
    thread_id: str
    timestamp: str
    user_query: str
    verdict: str
    reviewer_note: str | None
    reviewed_at: str
