"""
Phase 2 — RAG Ingestion Pipeline

Reads a policy PDF, chunks it, embeds, and stores in ChromaDB.

Embedding backend (controlled by EMBEDDING_BACKEND in .env):
  - "huggingface" (default): sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
    Runs fully locally, no AWS credentials required.
  - "bedrock": amazon.titan-embed-text-v2:0 via AWS Bedrock.
    Requires valid AWS credentials.

Usage:
    python scripts/ingest_policy.py
"""

import os
from pathlib import Path

import fitz  # PyMuPDF
from dotenv import load_dotenv
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

load_dotenv()

# ── Chunking parameters ────────────────────────────────────────────────────────
# chunk_size 900: large enough to keep a full policy clause together,
# small enough that retrieval returns focused results.
# chunk_overlap 175: ensures rules that span paragraph breaks aren't split.
CHUNK_SIZE = 900
CHUNK_OVERLAP = 175

COLLECTION_NAME = "holiday_policy"

HF_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _build_embeddings():
    """
    Return the embedding function based on EMBEDDING_BACKEND env var.
    Defaults to HuggingFace (local, no credentials needed).
    """
    backend = os.getenv("EMBEDDING_BACKEND", "huggingface").lower()

    if backend == "bedrock":
        from langchain_aws import BedrockEmbeddings
        profile = os.getenv("AWS_PROFILE", "default")
        return BedrockEmbeddings(
            model_id=os.getenv("BEDROCK_EMBEDDINGS", "amazon.titan-embed-text-v2:0"),
            region_name=os.getenv("AWS_DEFAULT_REGION", "eu-central-1"),
            credentials_profile_name=profile,
        )

    # Default: local HuggingFace model (no AWS needed)
    from langchain_huggingface import HuggingFaceEmbeddings
    print(f"[ingestor] Loading local model: {HF_MODEL}")
    return HuggingFaceEmbeddings(
        model_name=HF_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


# ── Step 1: Extract ───────────────────────────────────────────────────────────

def extract_pages(pdf_path: str) -> list[dict]:
    """
    Extract text from PDF page by page using PyMuPDF.

    Returns a list of dicts with keys: text, page, source.
    Empty or whitespace-only pages are skipped.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"Policy PDF not found: {pdf_path}")

    doc = fitz.open(str(path))
    pages = []
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text()
        if text.strip():
            pages.append({
                "text": text,
                "page": page_num,
                "source": path.name,
            })
    doc.close()
    return pages


# ── Step 2: Chunk ─────────────────────────────────────────────────────────────

def chunk_pages(pages: list[dict]) -> list[Document]:
    """
    Split page text into overlapping chunks.

    Separators are tried in order so clause boundaries are preferred
    over mid-sentence splits.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    documents: list[Document] = []
    for page_data in pages:
        chunks = splitter.split_text(page_data["text"])
        for i, chunk in enumerate(chunks):
            if chunk.strip():
                documents.append(Document(
                    page_content=chunk,
                    metadata={
                        "source": page_data["source"],
                        "page": page_data["page"],
                        "chunk_index": i,
                    },
                ))
    return documents


# ── Step 3 + 4: Embed & Store ─────────────────────────────────────────────────

def ingest(
    pdf_path: str,
    persist_dir: str | None = None,
) -> int:
    """
    Full ingestion pipeline: PDF → chunks → embeddings → ChromaDB.

    Embedding backend is controlled by EMBEDDING_BACKEND in .env
    ('huggingface' default, 'bedrock' when AWS credentials are available).
    """
    persist_dir = persist_dir or os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
    chroma_path = str(Path(persist_dir) / COLLECTION_NAME)

    print(f"[ingestor] Reading PDF: {pdf_path}")
    pages = extract_pages(pdf_path)
    print(f"[ingestor] Extracted {len(pages)} pages with content.")

    documents = chunk_pages(pages)
    print(f"[ingestor] Created {len(documents)} chunks "
          f"(size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}).")

    backend = os.getenv("EMBEDDING_BACKEND", "huggingface")
    print(f"[ingestor] Embedding backend: {backend}")
    embeddings = _build_embeddings()

    print(f"[ingestor] Storing in ChromaDB at: {chroma_path}")
    Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=chroma_path,
    )

    print(f"[ingestor] Done. {len(documents)} chunks stored in '{COLLECTION_NAME}'.")
    return len(documents)


def get_retriever(persist_dir: str | None = None, k: int = 5):
    """
    Return a retriever for the ingested policy collection.

    Used by the RAG agent node. Requires ingest() to have run at least once.
    """
    persist_dir = persist_dir or os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
    chroma_path = str(Path(persist_dir) / COLLECTION_NAME)

    embeddings = _build_embeddings()

    vectorstore = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=chroma_path,
    )
    return vectorstore.as_retriever(search_kwargs={"k": k})
