"""
Phase 2 — One-time ingestion script.

Run ONCE to build the ChromaDB vector store from the policy PDF:

    source .venv/bin/activate
    python scripts/ingest_policy.py

Re-running overwrites the collection (Chroma.from_documents replaces existing data).
"""

import sys
import time
from pathlib import Path

# Allow running from project root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingestion.policy_ingestor import ingest, get_retriever

PDF_PATH = "data/raw/Terms and conditions.pdf"


def main():
    print("=" * 60)
    print("  Cloudway — Policy Ingestion (Phase 2)")
    print("=" * 60)

    t0 = time.time()
    n_chunks = ingest(PDF_PATH)
    elapsed = time.time() - t0

    print(f"\n  Ingested {n_chunks} chunks in {elapsed:.1f}s.")

    # Quick retrieval smoke test
    print("\n[smoke test] Testing retrieval ...")
    retriever = get_retriever(k=3)
    results = retriever.invoke("cancellation fee 65 days before departure")
    print(f"  Query: 'cancellation fee 65 days before departure'")
    print(f"  Retrieved {len(results)} chunks:")
    for i, doc in enumerate(results, 1):
        snippet = doc.page_content[:120].replace("\n", " ")
        print(f"  [{i}] (page {doc.metadata.get('page', '?')}) {snippet}...")

    print("\nPhase 2 complete. ChromaDB is ready for the RAG agent.")


if __name__ == "__main__":
    main()
