# API Reference

## Module Overview

```
src/
├── state.py              — GuardrailsState TypedDict (shared contract)
├── graph.py              — build_graph() — wires all nodes
├── main.py               — CLI entry point (external loop)
├── telemetry.py          — OTel decorators + TRACER/METER
├── agents/
│   ├── rag_agent.py      — Agent 1: RAG + Claude
│   ├── classifier.py     — CLAIM/REFUSAL parser
│   ├── fact_extractor.py — Agent 2: NL → ASP atoms
│   ├── asp_validator.py  — Clingo validator
│   └── decision.py       — Final router
├── ingestion/
│   └── policy_ingestor.py — PDF → ChromaDB
└── persistence/
    └── audit_log.py       — JSONL/PostgreSQL logging
```

---

## `src/graph.py`

### `build_graph(checkpointer=None) → CompiledGraph`

Builds and compiles the LangGraph pipeline.

```python
from src.graph import build_graph
graph = build_graph()
result = graph.invoke(
    {"messages": [HumanMessage("What is the cancellation fee?")]},
    config={"configurable": {"thread_id": "session-001"}}
)
```

- `checkpointer=None` → uses `MemorySaver` (dev) or `PostgresSaver` (if `USE_POSTGRES_CHECKPOINTER=true`)
- Returns compiled graph; call `.invoke()` or `.stream()`

---

## `src/state.py`

### `GuardrailsState` (TypedDict)

Shared state passed between all nodes.

| Field | Type | Set by | Description |
|---|---|---|---|
| `messages` | `Sequence[BaseMessage]` | RAG Agent | Full conversation (appended per turn) |
| `retrieved_docs` | `list[str]` | RAG Agent | Top-5 policy chunks |
| `llm_answer` | `str` | RAG Agent | Raw LLM response text |
| `is_clarification` | `bool` | Classifier | True = no CLAIM/REFUSAL markers |
| `is_refusal` | `bool` | Classifier | True = REFUSAL: marker found |
| `classification_error` | `bool` | Classifier | True = both markers present |
| `extracted_claims` | `list[str]` | Fact Extractor | Raw CLAIM: line content |
| `extracted_facts` | `list[str]` | Fact Extractor | Validated ASP atoms |
| `validation_passed` | `bool` | ASP Validator | True = no violations |
| `violations` | `list[str]` | ASP Validator | Violation atoms from Clingo |
| `derived_facts` | `list[str]` | ASP Validator | All shown atoms from answer set |
| `decision` | `Literal[...]` | Router | Final routing outcome |

---

## `src/telemetry.py`

### `@node(node_name: str)` — decorator

Apply to every LangGraph node function. Adds full OTel stack.

```python
from src.telemetry import node, set_span_attrs

@node("my_node")
def my_node_function(state: GuardrailsState) -> dict:
    set_span_attrs({"my.metric": 42})
    return {"decision": "approved"}
```

### `set_span_attrs(attrs: dict) → None`

Attach key-value pairs to the current active OTel span.

```python
set_span_attrs({
    "classifier.has_claims": True,
    "asp.violations_count": 0,
    "rag.retrieved_chunks": 5,
})
```

### `TRACER` — `opentelemetry.trace.Tracer`

Use for the graph-level container span in `main.py`:

```python
from src.telemetry import TRACER

with TRACER.start_as_current_span("graph.run") as span:
    span.set_attribute("session.thread_id", thread_id)
    result = graph.invoke(...)
```

---

## `src/ingestion/policy_ingestor.py`

### `ingest(pdf_path: str, persist_dir: str = None) → int`

Full ingestion pipeline: PDF → chunks → embeddings → ChromaDB.

```python
from src.ingestion.policy_ingestor import ingest
n = ingest("data/raw/Terms and conditions.pdf")
# Returns number of chunks stored
```

**Environment variable:** `EMBEDDING_BACKEND=bedrock|huggingface` (default: `huggingface`)

### `get_retriever(persist_dir: str = None, k: int = 5) → Retriever`

Returns a LangChain retriever for the ingested policy collection.
Used by `rag_agent_node` — call `ingest()` at least once first.

---

## `src/persistence/audit_log.py`

### `log_turn(thread_id, user_query, llm_answer, extracted_facts, violations, decision, latency_ms) → None`

Write one audit record. Called after every `graph.invoke()`.

```python
from src.persistence.audit_log import log_turn
log_turn(
    thread_id="session-001",
    user_query="What is the cancellation fee?",
    llm_answer="CLAIM: ...",
    extracted_facts=["days_until_holiday(\"b1\", 65)."],
    violations=[],
    decision="approved",
    latency_ms=3846,
)
```

Backend: PostgreSQL if `USE_POSTGRES_CHECKPOINTER=true`, else `logs/audit.jsonl`.

### `query_logs(thread_id: str = None, limit: int = 50) → list[dict]`

Retrieve recent audit records (JSONL backend only).

---

## `src/agents/asp_validator.py`

### `asp_validator_node(state: GuardrailsState) → dict`

Can be called directly for testing with mock state:

```python
from src.agents.asp_validator import asp_validator_node

result = asp_validator_node({
    "extracted_facts": [
        'customer("c1").',
        'booking("c1", "b1").',
        'days_until_holiday("b1", 65).',
        'llm_claims_cancellation_fee("c1", "b1", 50).',  # wrong!
    ],
    # ... other state fields
})
# result["validation_passed"] = False
# result["violations"] = ['cancellation_claim_incorrect("c1","b1",50,"Incorrect cancellation fee")']
```

**Policy file:** `policies/holiday_policy.lp` — 228 lines, 28 clauses

---

## ASP Predicate Vocabulary

Full list of predicates the fact extractor may produce:

| Predicate | Arity | Meaning |
|---|---|---|
| `customer` | 1 | `customer("c1").` |
| `booking` | 2 | `booking("c1", "b1").` |
| `age` | 2 | `age("c1", 35).` |
| `has_adult_companion` | 1 | `has_adult_companion("c1").` |
| `days_until_holiday` | 2 | `days_until_holiday("b1", 65).` |
| `paid_full` | 2 | `paid_full("c1", "b1").` |
| `includes_flight` | 1 | `includes_flight("b1").` |
| `complaint_filed_days` | 3 | `complaint_filed_days("c1", "b1", 35).` |
| `injury_claim_filed_days` | 3 | `injury_claim_filed_days("c1", "b1", 45).` |
| `llm_approves_booking` | 2 | `llm_approves_booking("c1", "b1").` |
| `llm_rejects_booking` | 2 | `llm_rejects_booking("c1", "b1").` |
| `llm_claims_cancellation_fee` | 3 | `llm_claims_cancellation_fee("c1", "b1", 30).` |
| `llm_claims_fee` | 4 | `llm_claims_fee("c1", "b1", "name_change", 2500).` |

**Constraint:** All arguments must be ground (quoted strings or integers).
Variable-style arguments (`CustID`, `BookID`) are rejected by the regex validator.
