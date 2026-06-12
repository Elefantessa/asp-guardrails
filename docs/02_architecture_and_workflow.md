# Architecture & Workflow

## 1. Multi-Agent Graph (LangGraph)
The pipeline consists of the following components/nodes:

1. **User Interface/API:** Receives the user query.
2. **RAG Agent (Neural):** Manages dialog, retrieves context from ChromaDB, formats answers, and detects missing info.
3. **Classifier Node (Deterministic):** Parses the output of the RAG Agent.
    * If `CLAIM:` marker is found -> Routes to Fact Extraction Agent.
    * If `REFUSAL:` marker is found -> Routes to Decision Node (refused_out_of_scope).
    * If NO MARKER is found -> Routes to clarification loop (pauses state).
    * If conflicting markers (Both CLAIM and REFUSAL) -> Failsafe triggers immediate human escalation.
4. **Fact Extraction Agent (Neural):** Translates text claims into strict ASP atom syntax.
5. **ASP Validator (Symbolic):** Runs Clingo to mathematically verify facts against policy rules.
    * Output: Valid or Contradiction/Syntax Error.
6. **Decision Node (Deterministic):** Formulates the final workflow state.
    * `pending_info`: Halts graph to await user input.
    * `refused_out_of_scope`: Safely drops query.
    * `approved`: Verified by Clingo; safe to display. Logs stored in PostgreSQL.
    * `escalated`: Logic contradictions or syntax errors routed to Human Review.

## 2. Clarification Workflow (State Pause)
If the user asks a question missing required variables (e.g., cancellation days), the LangGraph node must reach the `END` state safely without waiting internally. PostgreSQL checkpointing saves the state. When the user replies, the application loop resumes execution at the `START` node with full memory context.