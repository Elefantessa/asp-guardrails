"""
Policy Ingestion Pipeline

Reads the clean markdown policy file, chunks it semantically, embeds,
and stores in ChromaDB.

Source: data/policy_text/Terms and conditions_raw.md
  → the markdown file IS the authoritative text artifact (no PDF extraction)

Two embedding backends produce two separate collections for comparison:
  - "bedrock"     → collection: holiday_policy_bedrock  (AWS Titan v2)
  - "huggingface" → collection: holiday_policy_hf       (local MiniLM)

Usage (via scripts/ingest_policy.py):
    python scripts/ingest_policy.py --embedding all        # both collections
    python scripts/ingest_policy.py --embedding bedrock
    python scripts/ingest_policy.py --embedding huggingface
"""

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

load_dotenv()

# Normalize any lowercase aws_* / bedrock_* env vars so boto3 can find them
for _k in list(os.environ.keys()):
    if _k.startswith(("aws_", "bedrock_")):
        os.environ.setdefault(_k.upper(), os.environ[_k])

# ── Chunking parameters ────────────────────────────────────────────────────────
CHUNK_SIZE = 900
CHUNK_OVERLAP = 175

# ── Collection name mapping ────────────────────────────────────────────────────
COLLECTION_FOR = {
    "bedrock":     "holiday_policy_bedrock",
    "huggingface": "holiday_policy_hf",
}

HF_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Regex: markdown heading lines (# / ## / ###)
_MD_HEADING_RE = re.compile(r"^#{1,3}\s+(.+)$")


# ── Embeddings factory ────────────────────────────────────────────────────────

def _build_embeddings(backend: str):
    if backend == "bedrock":
        from langchain_aws import BedrockEmbeddings
        return BedrockEmbeddings(
            model_id=os.getenv("BEDROCK_EMBEDDINGS", "amazon.titan-embed-text-v2:0"),
            region_name=os.getenv("AWS_DEFAULT_REGION", "eu-central-1"),
        )

    from langchain_huggingface import HuggingFaceEmbeddings
    print(f"[ingestor] Loading local model: {HF_MODEL}")
    return HuggingFaceEmbeddings(
        model_name=HF_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


# ── Stage 1: Read Markdown Artifact ──────────────────────────────────────────

def extract_from_markdown(md_path: str) -> tuple[str, Path]:
    """
    Read the clean markdown policy file. The .md file IS the text artifact —
    no PDF extraction needed.

    Strips the trailing metadata block (Source:, URL:, etc.) that appears
    after the final '---' separator in the file.

    Returns (clean_text, source_path).
    """
    path = Path(md_path)
    if not path.exists():
        raise FileNotFoundError(f"Policy markdown not found: {md_path}")

    text = path.read_text(encoding="utf-8")

    # Strip trailing metadata block (everything after the final horizontal rule)
    clean_text = text.split("\n---\n")[0].strip()

    print(f"[ingestor] Read markdown artifact → {path}  ({len(clean_text):,} chars)")
    return clean_text, path


# ── Stage 2: Markdown-Aware Chunking ─────────────────────────────────────────

def _extract_md_section_heading(text: str) -> str:
    """Return the first markdown heading found in the chunk text."""
    for line in text.splitlines():
        m = _MD_HEADING_RE.match(line.strip())
        if m:
            return m.group(1)[:80]
    return ""


def chunk_markdown(text: str, source_name: str) -> list[Document]:
    """
    Split markdown policy text into semantically aware overlapping chunks.

    Separator priority:
      1. ## heading  (major section boundary)
      2. ### heading (subsection boundary)
      3. Paragraph break (\\n\\n)
      4. Single newline
      5. Sentence boundary (". ")
      6. Word boundary (" ")

    Markdown tables (~250–350 chars each) are small enough to fit within
    a single 900-char chunk with surrounding context.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""],
    )

    documents: list[Document] = []
    for i, chunk in enumerate(splitter.split_text(text)):
        if chunk.strip():
            documents.append(Document(
                page_content=chunk,
                metadata={
                    "source":      source_name,
                    "chunk_index": i,
                    "section":     _extract_md_section_heading(chunk),
                },
            ))
    return documents


# ── Stage 3 + 4: Embed & Store ────────────────────────────────────────────────

def ingest(
    md_path: str,
    persist_dir: str | None = None,
    backend: str | None = None,
) -> int:
    """
    Full ingestion pipeline: markdown artifact → chunks → embeddings → ChromaDB.

    Args:
        md_path:     Path to the clean policy markdown file.
        persist_dir: Base directory for ChromaDB (default: CHROMA_PERSIST_DIR env var).
        backend:     "bedrock" | "huggingface" (default: EMBEDDING_BACKEND env var).

    Returns number of chunks stored.
    """
    backend = (backend or os.getenv("EMBEDDING_BACKEND", "huggingface")).lower()
    persist_dir = persist_dir or os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")

    collection_name = COLLECTION_FOR.get(backend)
    if collection_name is None:
        raise ValueError(f"Unknown backend '{backend}'. Choose 'bedrock' or 'huggingface'.")

    chroma_path = str(Path(persist_dir) / collection_name)

    print(f"\n[ingestor] ── Backend: {backend}  Collection: {collection_name} ──")
    print(f"[ingestor] Reading markdown: {md_path}")
    text, source_path = extract_from_markdown(md_path)

    documents = chunk_markdown(text, source_path.name)
    print(f"[ingestor] Created {len(documents)} chunks "
          f"(size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}).")

    embeddings = _build_embeddings(backend)
    print(f"[ingestor] Storing in ChromaDB at: {chroma_path}")
    Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        collection_name=collection_name,
        persist_directory=chroma_path,
    )

    print(f"[ingestor] Done. {len(documents)} chunks stored in '{collection_name}'.")
    return len(documents)


def get_vectorstore(
    persist_dir: str | None = None,
    backend: str | None = None,
):
    """
    Return the ChromaDB vectorstore for the given backend.
    Used by the RAG agent and the comparison script.
    """
    backend = (backend or os.getenv("EMBEDDING_BACKEND", "huggingface")).lower()
    persist_dir = persist_dir or os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
    collection_name = COLLECTION_FOR.get(backend, "holiday_policy_hf")
    chroma_path = str(Path(persist_dir) / collection_name)

    embeddings = _build_embeddings(backend)
    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=chroma_path,
    )


def get_retriever(persist_dir: str | None = None, k: int = 5, backend: str | None = None):
    """Return a retriever for the ingested policy collection (legacy helper)."""
    return get_vectorstore(persist_dir, backend).as_retriever(search_kwargs={"k": k})
