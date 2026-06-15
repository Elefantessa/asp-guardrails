"""
Phase 5 — Audit Logging

Every terminal state (approved, refused_out_of_scope, escalated, pending_info)
is logged as an immutable record.

Storage strategy:
  - If USE_POSTGRES_CHECKPOINTER=true → writes to PostgreSQL (audit_logs table,
    extracted_facts and violations stored as JSONB).
  - Otherwise → appends to logs/audit.jsonl as a fallback (development default).

Both modes produce the same schema so evaluation scripts can consume either.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_USE_PG = os.getenv("USE_POSTGRES_CHECKPOINTER", "false").lower() == "true"
_DB_URL = os.getenv("DATABASE_URL", "")
_JSONL_PATH = Path(os.getenv("AUDIT_LOG_PATH", "logs/audit.jsonl"))

# ── Singleton PostgreSQL connection pool ──────────────────────────────────────

_pg_conn = None


def _get_pg_conn():
    global _pg_conn
    if _pg_conn is None or _pg_conn.closed:
        import psycopg2
        _pg_conn = psycopg2.connect(_DB_URL)
        _pg_conn.autocommit = True
    return _pg_conn


# ── Public API ────────────────────────────────────────────────────────────────

def log_turn(
    thread_id: str,
    user_query: str,
    llm_answer: str,
    extracted_facts: list[str],
    violations: list[str],
    decision: str,
    latency_ms: int,
    retrieved_docs: list[str] | None = None,
    timestamp: str | None = None,
) -> str:
    """
    Write one audit record for a completed graph turn.

    Called after every graph.invoke() — regardless of decision outcome.
    Skips logging if decision is 'error' (unexpected state).

    Returns the ISO timestamp used in the record (so callers can build
    the turn_key = f"{thread_id}_{timestamp}" for review lookup).
    """
    if decision == "error":
        return ""

    ts = timestamp or datetime.now(timezone.utc).isoformat()
    record = {
        "thread_id": thread_id,
        "timestamp": ts,
        "user_query": user_query,
        "llm_answer": llm_answer,
        "retrieved_docs": [d[:300] for d in (retrieved_docs or [])],  # first 300 chars each
        "extracted_facts": extracted_facts,
        "violations": violations,
        "decision": decision,
        "latency_ms": latency_ms,
    }

    if _USE_PG and _DB_URL:
        _write_postgres(record)
    else:
        _write_jsonl(record)

    return ts


def query_logs(thread_id: str | None = None, limit: int = 50) -> list[dict]:
    """Return recent audit records (JSONL backend only for dev)."""
    if not _JSONL_PATH.exists():
        return []
    records = []
    with open(_JSONL_PATH) as f:
        for line in f:
            try:
                r = json.loads(line)
                if thread_id is None or r.get("thread_id") == thread_id:
                    records.append(r)
            except json.JSONDecodeError:
                continue
    return records[-limit:]


# ── Backends ──────────────────────────────────────────────────────────────────

def _write_postgres(record: dict) -> None:
    try:
        conn = _get_pg_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_logs
                    (thread_id, timestamp, user_query, llm_answer,
                     extracted_facts, violations, decision, latency_ms)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                """,
                (
                    record["thread_id"],
                    record["timestamp"],
                    record["user_query"],
                    record["llm_answer"],
                    json.dumps(record["extracted_facts"]),
                    json.dumps(record["violations"]),
                    record["decision"],
                    record["latency_ms"],
                ),
            )
    except Exception as exc:
        # Never crash the pipeline over a logging failure — fall through to JSONL
        _write_jsonl(record)
        print(f"[audit] PostgreSQL write failed, fell back to JSONL: {exc}")


def _write_jsonl(record: dict) -> None:
    _JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_JSONL_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")
