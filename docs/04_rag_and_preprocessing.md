# RAG System & Preprocessing Architecture

## 1. Document Ingestion & Parsing
* **Source Files:** The system will process corporate policy documents in PDF format.
* **Parsing Tool:** Use `PyMuPDF` (fitz) or `pdfplumber` for robust text extraction. Do NOT use simple loaders if they fail to preserve document structure (like tables or bullet points), as policy rules often rely on strict formatting.

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