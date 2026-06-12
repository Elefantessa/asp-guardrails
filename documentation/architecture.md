# System Architecture

## 1. Overview

Cloudway is a **neuro-symbolic** policy compliance system. It separates two responsibilities:

| Stage | Component | Guarantee |
|---|---|---|
| **Generation** | RAG Agent (Claude via Bedrock) | Natural, grounded answer |
| **Verification** | ASP Validator (Clingo) | Formal, decidable correctness |

Neither stage alone is sufficient. Together they provide answers that are both
fluent and formally verified against the policy.

---

## 2. Multi-Agent LangGraph Pipeline

```
START
  │
  ▼
┌─────────────────────────────────────────┐
│  AGENT 1: RAG Agent                     │
│  • Retrieves top-5 policy chunks        │
│  • Generates response via Claude        │
│  • Marks output: CLAIM: / REFUSAL: /    │
│    (no marker = clarification question) │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  CLASSIFIER (deterministic)             │
│  • Detects CLAIM: → final answer        │
│  • Detects REFUSAL: → out-of-scope      │
│  • No marker → clarification            │
└──────────────────┬──────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
   clarification /       final answer
   refusal / error            │
        │                     ▼
        │    ┌─────────────────────────────┐
        │    │  AGENT 2: Fact Extractor    │
        │    │  • Parses CLAIM: lines      │
        │    │  • Converts to ASP atoms    │
        │    │  • Validates syntax (regex) │
        │    └──────────────┬──────────────┘
        │                   │
        │                   ▼
        │    ┌─────────────────────────────┐
        │    │  ASP VALIDATOR (Clingo)     │
        │    │  • Combines facts + policy  │
        │    │  • Derives answer set       │
        │    │  • Detects violations       │
        │    └──────────────┬──────────────┘
        │                   │
        └──────────┬─────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  ROUTER (deterministic)                 │
│  • pending_info                         │
│  • refused_out_of_scope                 │
│  • approved  (ASP: no violations)       │
│  • escalated (ASP: violations found)    │
└──────────────────┬──────────────────────┘
                   │
                  END
```

---

## 3. Component Specifications

### 3.1 RAG Agent (`src/agents/rag_agent.py`)

| Property | Value |
|---|---|
| Model | `eu.anthropic.claude-sonnet-4-6` via AWS Bedrock |
| Temperature | 0 (deterministic) |
| Max tokens | 2,000 |
| Retrieval | ChromaDB `holiday_policy` collection, k=5 |
| Embeddings | Bedrock Titan Embed v2 (`amazon.titan-embed-text-v2:0`), 1024 dims |
| Profile | `credentials_profile_name=AWS_PROFILE` |

**System prompt behavior:**
- Rule 1: Answer grounded in policy only — never invent values
- Rule 2: Ask for missing info before answering (slot detection)
- Rule 3: Prepend every factual claim with `CLAIM:`
- Rule 4: Prepend out-of-scope refusals with `REFUSAL: out_of_scope`
- Rule 5: No markers in clarification questions

### 3.2 Classifier (`src/agents/classifier.py`)

Pure string matching — no LLM call, no latency.

```python
has_claims  = any(line.startswith("CLAIM:") for line in lines)
has_refusal = any(line.startswith("REFUSAL:") for line in lines)
```

| State | `is_clarification` | `is_refusal` | `classification_error` |
|---|---|---|---|
| Clarification question | True | False | False |
| Final factual answer | False | False | False |
| Out-of-scope refusal | False | True | False |
| Both markers (bug) | False | False | True → escalated |

### 3.3 Fact Extraction Agent (`src/agents/fact_extractor.py`)

| Property | Value |
|---|---|
| Model | Same as RAG agent (reuses `BEDROCK_LLM`) |
| Temperature | 0 |
| Max tokens | 800 (facts only, no prose) |
| Vocabulary | 13 predicates (customer, booking, age, days_until_holiday, …) |
| Validation | Regex: `^[a-z][a-z_]*\("…"|\d+(,…)*\)\.$` |

**Vocabulary (13 predicates):**
```
customer/1, booking/2, age/2, has_adult_companion/1,
days_until_holiday/2, paid_full/2, includes_flight/1,
complaint_filed_days/3, injury_claim_filed_days/3,
llm_approves_booking/2, llm_rejects_booking/2,
llm_claims_cancellation_fee/3, llm_claims_fee/4
```

**Known limitation:** Claims outside this vocabulary (ATOL, ABTA, extraordinary
circumstances) produce no facts → answer escalated as unverifiable.
This is intentional: the system prefers false escalation over false approval.

### 3.4 ASP Validator (`src/agents/asp_validator.py`)

| Property | Value |
|---|---|
| Solver | Clingo 5.8.0 (Python API) |
| Policy file | `policies/holiday_policy.lp` (228 lines, 28 clauses) |
| Latency | < 15 ms |
| Output | `shown=True` atoms via `#show` directives |

**Violation predicates detected:**
```
answer_invalid/3, cancellation_claim_incorrect/4,
fee_claim_incorrect/5, booking_invalid/3,
lead_name_invalid/2, minor_unaccompanied/3,
complaint_invalid/3, injury_claim_invalid/3
```

### 3.5 Telemetry (`src/telemetry.py`)

OTel decorator hierarchy (applied to every node):

```
@node("name")
  = @traced      — opens span "node.<name>"
    @counted     — increments cloudway.node.executions counter
      @timed     — records cloudway.node.latency_ms histogram
        @track_errors  — records exceptions on span
```

Graph-level span: `with TRACER.start_as_current_span("graph.run")` in `main.py`.
Export: OTLP gRPC to Grafana LGTM on `localhost:4317`.

---

## 4. State Schema (`src/state.py`)

```python
class GuardrailsState(TypedDict):
    messages:             Annotated[Sequence[BaseMessage], add_messages]
    retrieved_docs:       list[str]
    llm_answer:           str
    is_clarification:     bool
    is_refusal:           bool
    classification_error: bool
    extracted_claims:     list[str]
    extracted_facts:      list[str]
    validation_passed:    bool
    violations:           list[str]
    derived_facts:        list[str]
    decision:             Literal["pending_info","refused_out_of_scope","approved","escalated","error"]
```

`messages` uses `add_messages` reducer — appends per turn, preserving multi-turn history.

---

## 5. Persistence

### 5.1 LangGraph Checkpointing

| Mode | Config | Usage |
|---|---|---|
| `MemorySaver` | `USE_POSTGRES_CHECKPOINTER=false` | Development (default) |
| `PostgresSaver` | `USE_POSTGRES_CHECKPOINTER=true` | Production |

Each `graph.invoke()` with the same `thread_id` restores full conversation state.
This is the mechanism enabling multi-turn clarification without internal graph loops.

### 5.2 Audit Logging (`src/persistence/audit_log.py`)

Every turn is logged regardless of decision:

```json
{
  "thread_id": "session-001",
  "timestamp": "2026-06-04T06:38:37Z",
  "user_query": "What is the cancellation fee?",
  "llm_answer": "...",
  "extracted_facts": ["days_until_holiday(\"b1\", 65).", "..."],
  "violations": [],
  "decision": "approved",
  "latency_ms": 3846
}
```

Backend: PostgreSQL (JSONB) when configured, JSONL file (`logs/audit.jsonl`) otherwise.

---

## 6. The External Loop Pattern

LangGraph cannot pause to wait for user input. The conversation loop lives
**outside** the graph in `src/main.py`:

```python
while True:
    user_input = input()
    result = graph.invoke(
        {"messages": [HumanMessage(user_input)]},
        config={"thread_id": session_id}  # restores checkpoint automatically
    )
    display(result)
```

Each `graph.invoke()` runs START→END. State is checkpointed at END.
The next invocation with the same `thread_id` restores the full history.

This pattern enables:
- Stateless graph runs (horizontal scaling)
- Server restarts without losing conversations
- The same graph usable from CLI, web, or API
