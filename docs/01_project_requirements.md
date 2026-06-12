# Project Requirements: Cloudway (Neuro-Symbolic Policy Compliance)

## 1. Goal
Build a strict policy chatbot that completely eliminates undetected hallucinations by combining Neural Generation (RAG) with Symbolic Verification (ASP). False escalation to a human is rigorously preferred over a mathematically false approval.

## 2. Tech Stack & Constraints
* **LLM:** Claude 4.6 Sonnet via AWS Bedrock. MUST run at `Temperature = 0` for output reproducibility.
* **Orchestration:** LangGraph. Used for multi-node orchestration, clear state transitions, and native checkpointing.
* **Retrieval/Vector Store:** ChromaDB. Chosen for local, persistent, and low-latency vector storage.
* **Persistence & Logging:** PostgreSQL.
    * Must store LangGraph checkpoints for perfect conversation reproducibility.
    * Must use `JSONB` format to store immutable audit logs of complex intermediate multi-agent states.
* **Symbolic Validation:** Answer Set Programming (ASP) using the `clingo` python library.
* **LangChain Strict Minimization:** LangChain is permitted ONLY as integration glue (wrappers). Permitted uses: `ChatBedrock` wrapper, `BedrockEmbeddings` wrapper, `Chroma` retriever wrapper. DO NOT use LangChain agents or complex memory modules; rely on LangGraph and pure Python.

## 3. Core Design Principle
The LLM acts as both a conversational answerer and a slot (missing-information) detector. Irrelevant answers skip symbolic validation to prevent syntax crashes.
