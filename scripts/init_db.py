"""
Phase 1 database initialisation script.

Run once before starting the system:
    python scripts/init_db.py

What this does:
  1. PostgreSQL — creates the audit_logs table.
     (LangGraph's PostgresSaver creates its own checkpoint tables via .setup().)
  2. ChromaDB   — verifies the local persist directory is accessible and
                  creates the 'policy_documents' collection if it doesn't exist.

Set DATABASE_URL and CHROMA_PERSIST_DIR in your .env (copy from .env.example).
"""

import os
import sys
from pathlib import Path

# Allow running from project root: python scripts/init_db.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────────────────────────────────────
# PostgreSQL
# ──────────────────────────────────────────────────────────────────────────────

AUDIT_LOGS_DDL = """
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id       SERIAL PRIMARY KEY,
    thread_id    TEXT        NOT NULL,
    timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_query   TEXT        NOT NULL,
    llm_answer   TEXT,
    extracted_facts JSONB,
    violations   JSONB,
    decision     TEXT,
    latency_ms   INTEGER
);

CREATE INDEX IF NOT EXISTS audit_logs_thread_id_idx ON audit_logs (thread_id);
CREATE INDEX IF NOT EXISTS audit_logs_decision_idx  ON audit_logs (decision);
"""


def init_postgres() -> None:
    database_url = os.getenv("DATABASE_URL")
    use_postgres = os.getenv("USE_POSTGRES_CHECKPOINTER", "false").lower() == "true"

    if not use_postgres:
        print("[postgres] USE_POSTGRES_CHECKPOINTER=false — skipping (MemorySaver will be used).")
        return

    if not database_url:
        print("[postgres] ERROR: DATABASE_URL is not set in .env.", file=sys.stderr)
        sys.exit(1)

    try:
        import psycopg2
    except ImportError:
        print("[postgres] ERROR: psycopg2-binary not installed. Run: pip install psycopg2-binary", file=sys.stderr)
        sys.exit(1)

    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(AUDIT_LOGS_DDL)
        conn.close()
        print("[postgres] audit_logs table ready.")

        # LangGraph PostgresSaver creates its own tables; we trigger .setup() here
        # so it runs at init time rather than at first graph.invoke().
        from langgraph.checkpoint.postgres import PostgresSaver
        saver = PostgresSaver.from_conn_string(database_url)
        saver.setup()
        print("[postgres] LangGraph checkpoint tables ready.")

    except Exception as exc:
        print(f"[postgres] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# ChromaDB
# ──────────────────────────────────────────────────────────────────────────────

def init_chromadb() -> None:
    persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
    Path(persist_dir).mkdir(parents=True, exist_ok=True)

    try:
        import chromadb
    except ImportError:
        print("[chromadb] ERROR: chromadb not installed. Run: pip install chromadb", file=sys.stderr)
        sys.exit(1)

    client = chromadb.PersistentClient(path=persist_dir)

    # Phase 2 ingestion will populate this collection.
    collection = client.get_or_create_collection(
        name="policy_documents",
        metadata={"hnsw:space": "cosine"},
    )
    print(f"[chromadb] Collection 'policy_documents' ready at '{persist_dir}' "
          f"({collection.count()} chunks stored).")


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Cloudway — database init ===\n")
    init_postgres()
    init_chromadb()
    print("\nDone. Phase 1 databases ready.")
