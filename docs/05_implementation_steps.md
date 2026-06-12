# Implementation Roadmap & Step-by-Step Guide

Please implement the Cloudway system following this exact sequence:

## Phase 1: Environment & Foundations
1. **Initialize Project:** Create virtual environment, standard directory structure (`src`, `data`, `notebooks`, `tests`).
2. **Dependencies:** Write a comprehensive `requirements.txt` including: `langgraph`, `langchain-aws`, `boto3`, `chromadb`, `psycopg2-binary` (or `asyncpg`), `clingo`, `sentence-transformers`, `langchain-huggingface`, `PyMuPDF`.
3. **Database Setup:** * Write a utility script to initialize the PostgreSQL database schema (for LangGraph checkpointer and audit logs).
    * Set up the local ChromaDB client instance.

## Phase 2: The RAG Pipeline (Ingestion)
1. **Document Loader:** Write a script to ingest a sample policy PDF from a `data/raw/` folder.
2. **Preprocessing:** Implement the `RecursiveCharacterTextSplitter` logic.
3. **Embedding:** Integrate `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
4. **Vectorization:** Script to process chunks, embed them, and store them in ChromaDB with metadata.

## Phase 3: ASP Validator (Symbolic Logic)
1. **Clingo Setup:** Create a Python module that interfaces with `clingo`.
2. **Policy Translation:** Write a sample ASP program (e.g., `policy.lp`) that defines a basic rule (like the holiday cancellation fee rule).
3. **Validation Function:** Write a function that takes an extracted claim (formatted as an ASP fact), runs the Clingo solver against the rules, and returns a strict Valid/Invalid result.

## Phase 4: LangGraph Orchestration (The Core)
1. **State Definition:** Define the `TypedDict` for the graph state (messages, missing_info_flags, validation_results, etc.).
2. **Node Implementation:**
    * `rag_agent`: Connects to Claude 3.5 Sonnet (Temp=0), uses the defined system prompt, queries ChromaDB, and generates output.
    * `classifier_node`: Parses the LLM string for `CLAIM:` or `REFUSAL:`.
    * `fact_extractor`: Extracts the core parameters from a CLAIM to feed into ASP.
    * `asp_validator`: Calls the function built in Phase 3.
    * `decision_node`: Determines the final state.
3. **Graph Construction:** Link the nodes using LangGraph's `StateGraph`, adding conditional edges based on the classifier and validator outputs.
4. **Checkpointer:** Attach the PostgreSQL checkpointer to the graph to enable the clarification pause/resume workflow.

## Phase 5: Testing & Audit Logging
1. Write a test script simulating a complete conversation loop, including a missing-information pause.
2. Ensure every terminal state (approved, refused, escalated) logs the final graph state as JSONB to PostgreSQL.