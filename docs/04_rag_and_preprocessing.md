# RAG System & Preprocessing Architecture

## 1. Document Ingestion & Parsing

**Source file:** `data/policy_text/Terms and conditions_raw.md`

The system uses a clean manually-sourced markdown file as its authoritative policy
artifact — not the original PDF. The PDF's first page used a custom font that shifted
every character's codepoint by −29, producing garbled output (e.g. `:KHQ\RX` instead of
"When you"). The payment deadline rules lived on that page, so TC008 and related cases
failed consistently (see ISS-001 in `docs/08_issues_and_fixes.md`).

**Ingestion function:** `extract_from_markdown()` in `src/ingestion/policy_ingestor.py`
- Reads the `.md` file and strips the trailing metadata block (after the final `---`)
- Passes clean text to `chunk_markdown()` with heading-aware separators:
  `["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""]`

**Metadata per chunk:** `source`, `chunk_index`, `section` (nearest `##`/`###` heading).
No `page` field — not meaningful for a single markdown file.

**Dual collections:**

| Collection | Embedding model | Backend | Dims |
|---|---|---|---|
| `holiday_policy_bedrock` | `amazon.titan-embed-text-v2:0` | AWS Bedrock | 1024 |
| `holiday_policy_hf` | `paraphrase-multilingual-MiniLM-L12-v2` | HuggingFace local | 384 |

Active collection selected by `EMBEDDING_BACKEND` env var (default: `bedrock`).
Run `python scripts/ingest_policy.py --embedding bedrock` (or `--embedding huggingface`) to populate.

## 2. Text Chunking Strategy (Semantic & Structural)
Policy documents require careful chunking to ensure that conditions and their corresponding rules are not split across different chunks.
* **Tool:** Use `RecursiveCharacterTextSplitter` from LangChain (as a utility wrapper).
* **Parameters:**
    * `chunk_size`: 800 - 1000 characters.
    * `chunk_overlap`: 150 - 200 characters (critical for maintaining context between policy clauses).
* **Metadata:** Each chunk MUST retain metadata indicating its source document, page number, and (if possible) the policy section heading. This is vital for the LLM to ground its claims accurately.

## 3. Embedding Model
* **Model Choice:** Use the specific multilingual Sentence Transformers model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
* **Implementation:** Load this model locally using the `HuggingFaceEmbeddings` wrapper from `langchain-huggingface`. 
* **Justification:** This model is chosen for its balance of performance and efficiency, and its ability to handle potential multilingual policy variations if needed in the future.

## 4. Vector Store (ChromaDB) Configuration
* **Persistence:** The ChromaDB instance MUST be configured to save locally to a specific directory (e.g., `./chroma_db`).
* **Collection:** Create a dedicated collection named `policy_documents`.
* **Retrieval:** Configure the retriever to fetch the top `k=4` or `k=5` most relevant chunks per query.