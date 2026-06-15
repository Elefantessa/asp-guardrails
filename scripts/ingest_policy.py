"""
Policy Ingestion Script

Builds ChromaDB vector store(s) from the clean markdown policy file.

Source: data/policy_text/Terms and conditions_raw.md
  (The markdown file is the authoritative text artifact — no PDF extraction needed)

Usage:
    python scripts/ingest_policy.py                    # both backends (default)
    python scripts/ingest_policy.py --embedding all
    python scripts/ingest_policy.py --embedding bedrock
    python scripts/ingest_policy.py --embedding huggingface

After ingestion, the vocabulary generation step runs automatically to produce:
    policies/predicate_signatures.json
    policies/vocabulary_map.json
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingestion.policy_ingestor import ingest, get_retriever

MD_PATH = "data/policy_text/Terms and conditions_raw.md"


def run_ingestion(backend: str) -> int:
    t0 = time.time()
    n_chunks = ingest(MD_PATH, backend=backend)
    elapsed = time.time() - t0
    print(f"  [{backend}] Ingested {n_chunks} chunks in {elapsed:.1f}s.")

    # Smoke test
    retriever = get_retriever(k=3, backend=backend)
    results = retriever.invoke("cancellation fee 65 days before departure")
    print(f"  [{backend}] Smoke test — retrieved {len(results)} chunks:")
    for i, doc in enumerate(results, 1):
        section = doc.metadata.get("section", "")
        snippet = doc.page_content[:100].replace("\n", " ")
        label = f"§{section}" if section else "§(no heading)"
        print(f"    [{i}] ({label}) {snippet}...")
    return n_chunks


def main():
    parser = argparse.ArgumentParser(description="Ingest policy markdown into ChromaDB")
    parser.add_argument(
        "--embedding",
        choices=["bedrock", "huggingface", "all"],
        default="all",
        help="Embedding backend to use (default: all — creates both collections)",
    )
    args = parser.parse_args()

    print("=" * 64)
    print("  Cloudway — Policy Ingestion")
    print("=" * 64)

    backends = ["bedrock", "huggingface"] if args.embedding == "all" else [args.embedding]

    for backend in backends:
        try:
            run_ingestion(backend)
        except Exception as exc:
            print(f"  [{backend}] FAILED: {exc}")
            if args.embedding != "all":
                raise
            print(f"  [{backend}] Skipping this backend and continuing...")

    # Generate vocabulary artifacts (predicates + vocab map)
    print("\n[ingest] Running vocabulary generation...")
    try:
        from scripts.generate_vocabulary import generate_vocabulary
        predicate_count, vocab_count = generate_vocabulary()
        print(f"[ingest] Generated {predicate_count} predicates, "
              f"{vocab_count} vocabulary mappings.")
    except Exception as exc:
        print(f"[ingest] Vocabulary generation skipped: {exc}")

    print("\nIngestion complete. Collections ready for the RAG agent.")


if __name__ == "__main__":
    main()
