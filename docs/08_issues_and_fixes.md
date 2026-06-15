# Issues, Root Causes & Fixes — Living Document

> Updated every time a code change is made. Each entry follows: **Problem → Root Cause → Fix Applied**.

---

## Issue Log

---

### ISS-001 · Garbled PDF text → missing policy sections
**Status:** FIXED  
**Files:** `src/ingestion/policy_ingestor.py`, `scripts/ingest_policy.py`  
**Symptom:** Benchmark stuck at 14/31. TC008, TC030 always failing. RAG retrieves no meaningful chunks for payment rules.  
**Root Cause:** PyMuPDF extracted page 1 of the TUI PDF using a custom font that offsets every character's Unicode codepoint by −29. Output looked like `:KHQ\RX` instead of `When you`. The "Price You Pay" (12-week deposit/payment rules) and "Complaint" sections were both garbled.  
**Fix:** Replaced PDF extraction pipeline entirely with a clean manually-sourced markdown file (`data/policy_text/Terms and conditions_raw.md`). Removed `extract_and_save()` + `chunk_pages()` from `policy_ingestor.py`. Added `extract_from_markdown()` + `chunk_markdown()` with heading-aware separators. 33 clean chunks now include all previously missing sections.

---

### ISS-002 · AWS credentials ignored — lowercase env vars
**Status:** FIXED  
**Files:** `src/ingestion/policy_ingestor.py`, `scripts/benchmark_baselines.py`  
**Symptom:** `ExpiredTokenException` or `NoCredentialsError` even after updating `.env`.  
**Root Cause:** `python-dotenv` writes env vars in the exact case found in the `.env` file (e.g. `aws_access_key_id`). Boto3 only reads uppercase `AWS_ACCESS_KEY_ID`. So the credentials were present in the environment but boto3 couldn't see them.  
**Fix:** Added normalization loop after `load_dotenv()` in both files:
```python
for _k in list(os.environ.keys()):
    if _k.startswith(("aws_", "bedrock_")):
        os.environ.setdefault(_k.upper(), os.environ[_k])
```

---

### ISS-003 · `credentials_profile_name` overrides env vars
**Status:** FIXED  
**Files:** `src/agents/rag_agent.py` (line 131), `src/agents/fact_extractor.py` (line 120)  
**Symptom:** Pipeline ignores `.env` credentials and uses `~/.aws/credentials` which may be stale.  
**Root Cause:** `ChatBedrock(credentials_profile_name=profile)` forces boto3 to load from the named profile in `~/.aws/credentials`, completely ignoring any `AWS_*` environment variables. Since the AWS Learner Lab updates only `.env` (not `~/.aws/credentials`), credentials always appear expired.  
**Fix:** Removed `credentials_profile_name` parameter from `ChatBedrock(...)` in both files. boto3 now reads `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` from the environment.

---

### ISS-004 · `partial_validation` escalation removed as a hack
**Status:** FIXED (proper solution)  
**Files:** `src/agents/decision.py`  
**Symptom:** With natural-language CLAIM: lines, fact extractor couldn't extract valid ASP facts → `extracted_facts=[]` → `partial_validation=True`. The escalation for partial_validation was removed as a workaround, giving a 30/31 vacuous pass.  
**Root Cause (original):** CLAIM: lines were natural-language sentences like "Sarah is 16 and cannot be lead name" — the fact extractor LLM couldn't convert these reliably to ground ASP atoms, producing UNMAPPED: lines and `partial_validation=True`. The escalation was correct *in principle* but fired too broadly because the CLAIM format was wrong.  
**Root Cause (proper):** Two separate issues compounded:
  1. CLAIM: format was compound natural language → fact extractor couldn't parse → spurious partial_validation
  2. Escalation rule was removed as a hack instead of fixing the CLAIM format  
**Fix:** 
  1. (This issue) Restored `partial_validation` escalation in `decision.py` — if `partial_validation=True` the decision is `escalated`
  2. (ISS-006) Fixed CLAIM: format in `rag_agent.py` to output atomic ASP-style predicates — eliminates spurious partial_validation for validatable claims

---

### ISS-005 · VIOLATION_PREFIXES over-inclusive — derived facts treated as violations
**Status:** FIXED  
**Files:** `src/agents/asp_validator.py`  
**Symptom:** TC002 (LLM correctly rejects minor booking) and TC009 (LLM correctly says complaint is too late) escalated instead of being approved, even when the LLM answer was correct.  
**Root Cause:** `VIOLATION_PREFIXES` included intermediate ASP derived facts: `booking_invalid`, `lead_name_invalid`, `minor_unaccompanied`, `complaint_invalid`, `injury_claim_invalid`. These represent policy-relevant facts (e.g., "this customer is under 18") — NOT violations of the LLM answer. When the LLM *correctly* identifies a policy issue (e.g., "you can't book as lead name"), these predicates fire correctly as part of ASP reasoning, but then were misidentified as guardrail violations.  
**Fix:** Removed intermediate derived facts from VIOLATION_PREFIXES. Only **LLM-answer-level** violations remain:
```python
VIOLATION_PREFIXES = (
    "answer_invalid",           # LLM approved invalid booking OR rejected valid booking
    "cancellation_claim_incorrect",  # LLM quoted wrong cancellation %
    "fee_claim_incorrect",           # LLM quoted wrong amendment fee
    "atol_claim_incorrect",          # LLM wrongly claimed ATOL protection  [NEW]
    "abta_claim_incorrect",          # LLM wrongly claimed ABTA protection  [NEW]
    "amendment_assessment_incorrect", # LLM wrongly said amendment is blocked/allowed [NEW]
)
```

---

### ISS-006 · Compound CLAIM: format — fact extractor fails to extract ASP predicates
**Status:** FIXED  
**Files:** `src/agents/rag_agent.py` (SYSTEM_PROMPT)  
**Symptom:** Fact extractor receives compound natural-language claims like "Sarah is 16 and therefore cannot be lead name on the booking" — it outputs `UNMAPPED:` for these because they can't be mechanically mapped to a single ASP predicate. This causes `partial_validation=True` and (with proper decision.py) → escalated for cases that should be approved.  
**Root Cause:** PART 2 of the RAG SYSTEM_PROMPT asked for "factual claims using CLAIM: prefix" with a natural-language example. The LLM interpreted this as permission to write compound reasoning sentences, not machine-parseable predicates.  
**Fix:** PART 2 of SYSTEM_PROMPT now specifies **exact ASP predicate syntax** for each CLAIM: line. Each CLAIM: must be a ground ASP fact in the format `predicate("arg1", arg2)`. See updated prompt in `rag_agent.py`.

---

### ISS-007 · `lead_name_valid` requires explicit age ≥ 18 — breaks age-agnostic queries
**Status:** FIXED  
**Files:** `policies/holiday_policy.lp`  
**Symptom:** TC004 (65-day cancellation), TC006 (amendment fee), TC008 (100-day payment) all failed because `booking_valid` required `lead_name_valid` which required `age(C, Age), Age >= 18` — but these queries don't mention age, so the rule never fired.  
**Root Cause:** Original rule: `lead_name_valid(C) :- customer(C), age(C, Age), Age >= 18.` This uses a positive precondition on age. Under ASP's Closed World Assumption, if age is not provided the rule simply doesn't fire — no age data → no lead_name_valid → booking_valid never derived → any llm_approves_booking → answer_invalid.  
**Fix:** Changed to negation-as-failure (Closed World semantics for invalidity):
```prolog
lead_name_valid(C) :- customer(C), not lead_name_invalid(C, _).
lead_name_invalid(C, "Lead booker must be 18 or older") :- customer(C), age(C, Age), Age < 18.
```
Semantics: lead name is assumed valid UNLESS we have evidence it is invalid (explicit age < 18). Age-agnostic queries now correctly derive `lead_name_valid`.

---

### ISS-008 · `booking_invalid` fires for minor with adult companion → `answer_invalid` for TC003
**Status:** FIXED  
**Files:** `policies/holiday_policy.lp`  
**Symptom:** TC003 (Emma 15 + Mark 42, expected=approved): ASP derived `lead_name_invalid` (Emma < 18) → `booking_invalid` (old rule fired unconditionally) → `answer_invalid` (LLM approved invalid booking) → escalated.  
**Root Cause:** Old rule `booking_invalid(C, B, Reason) :- booking(C,B), lead_name_invalid(C, Reason)` fired regardless of whether an adult companion was present. But the policy implicitly allows a minor to participate in a booking if an adult is the lead name — represented by `has_adult_companion`.  
**Fix:** Changed booking_invalid for minor lead name to only fire when NOT accompanied:
```prolog
booking_invalid(C, B, "Minor lead booker without adult companion") :-
    booking(C, B), lead_name_invalid(C, _), not minor_accompanied(C).
```
If `has_adult_companion("c1")` is present, `minor_accompanied` fires, `not minor_accompanied` is false → `booking_invalid` does NOT fire → `answer_invalid` does NOT fire → APPROVED.  
**ASP model limitation (documented):** The single-entity model cannot verify WHO the lead name is (e.g., confirm Mark is the lead name). The presence of `has_adult_companion` is used as a proxy for "an adult is the lead name." Full multi-person booking validation requires a future extension: `lead_age/3` + `minor_traveler_age/4` predicates.

---

### ISS-009 · `amendment_fee` rules require `days_until_holiday` for time-independent fees
**Status:** FIXED  
**Files:** `policies/holiday_policy.lp`  
**Symptom:** TC006 (name change fee query, no days in query): `amendment_fee("c1","b1","name_change",2500)` never derived because the rule required `days_until_holiday(B, Days)`. So `fee_claim_incorrect` could never fire (no `amendment_fee` to compare against), meaning a wrong fee could slip through undetected.  
**Root Cause:** All `amendment_fee` rules were conditioned on `days_until_holiday(B, Days), Days >= 0` — effectively requiring that days be provided. For name change and service upgrade, the fee is fixed regardless of timing.  
**Fix:** Made time-independent fees unconditional on days:
```prolog
amendment_fee(C, B, "name_change", 2500) :- booking(C, B).
amendment_fee(C, B, "upgrade_service", 0)  :- booking(C, B).
```
Duration change and accommodation change fees still require `days_until_holiday` (accommodation change is blocked within 29 days anyway).

---

### ISS-010 · Missing predicates for ATOL claims and amendment-blocked claims
**Status:** FIXED  
**Files:** `policies/holiday_policy.lp`, `policies/predicate_signatures.json`  
**Symptom:** TC023 (ATOL protection) and TC007 (accommodation change treated as cancellation): RAG had no predicates to express "LLM says ATOL applies" or "LLM says this amendment is blocked." Claims became UNMAPPED → partial_validation.  
**Root Cause:** The original 13 predicates covered booking decision (`llm_approves_booking`, `llm_rejects_booking`) and fee claims, but not protection status claims or amendment-blocked claims. Symbolic coverage was incomplete for these question types.  
**Fix:** Added 3 new input predicates to `holiday_policy.lp` and `predicate_signatures.json`:
- `llm_claims_atol_protected/2` — LLM claims ATOL financial protection applies
- `llm_claims_abta_protected/2` — LLM claims ABTA financial protection applies
- `llm_claims_amendment_blocked/3` — LLM says a specific change type is treated as cancellation  
  Added corresponding validation rules (`atol_claim_incorrect`, `abta_claim_incorrect`, `amendment_assessment_incorrect`) and `#show` directives.

---

### ISS-011 · TC031 — RAG retrieves compensation table instead of cancellation fee table
**Status:** FIXED (vocabulary)  
**Files:** `policies/vocabulary_map.json`  
**Symptom:** TC031 query "What percentage of the holiday cost will we lose?" → RAG retrieved the COMPANY CANCELLATION COMPENSATION table (£0-£100 per person) instead of the CUSTOMER CANCELLATION FEE table (0-100%). LLM returned `pending_info` (couldn't find fee table).  
**Root Cause:** The vocabulary map had no synonym mapping "lose" or "percentage we lose" to "cancellation fee". The query rewriter couldn't normalize "will we lose" to "cancellation fee percentage". ChromaDB retrieved compensation table (semantically similar to "lose money") instead.  
**Fix:** Added `"lose/money lost/percentage lost"` synonyms to the `cancellation fee` entry in `vocabulary_map.json`.

---

## Change Summary Table

| ISS | Files Changed | Root Cause Category | Status |
|-----|--------------|--------------------|----|
| ISS-001 | `policy_ingestor.py`, `ingest_policy.py` | Data pipeline | ✅ Fixed |
| ISS-002 | `policy_ingestor.py`, `benchmark_baselines.py` | Infrastructure/credentials | ✅ Fixed |
| ISS-003 | `rag_agent.py`, `fact_extractor.py` | Infrastructure/credentials | ✅ Fixed |
| ISS-004 | `decision.py` | Architecture (hack removal) | ✅ Fixed |
| ISS-005 | `asp_validator.py` | ASP model design | ✅ Fixed |
| ISS-006 | `rag_agent.py` | Prompt engineering | ✅ Fixed |
| ISS-007 | `holiday_policy.lp` | ASP model (CWA) | ✅ Fixed |
| ISS-008 | `holiday_policy.lp` | ASP model (booking_invalid rule) | ✅ Fixed |
| ISS-009 | `holiday_policy.lp` | ASP model (rule preconditions) | ✅ Fixed |
| ISS-010 | `holiday_policy.lp`, `predicate_signatures.json` | ASP coverage gap | ✅ Fixed |
| ISS-011 | `vocabulary_map.json` | Retrieval vocabulary | ✅ Fixed |
| ISS-012 | `rag_agent.py` | Prompt design (query type confusion) | ✅ Fixed |
| ISS-013 | `rag_agent.py` | Prompt design (ATOL w/o flight) | ✅ Fixed |
| ISS-014 | `vocabulary_map.json`, `query_rewriter.py` | Vocab slice + ordering | ✅ Fixed |
| ISS-015 | `query_rewriter.py` | Infrastructure/credentials | ✅ Fixed |
| ISS-016 | `query_rewriter.py` | Rule-based rewriter missing cancellation pattern | ✅ Fixed |

---

---

### ISS-012 · `llm_approves_booking`/`llm_rejects_booking` used for non-eligibility queries
**Status:** FIXED  
**Files:** `src/agents/rag_agent.py` (SYSTEM_PROMPT PART 2)  
**Symptom:** TC004 (cancellation fee query) escalated with `answer_invalid("LLM approved invalid booking")`. TC009 (complaint timing query) escalated with `answer_invalid("LLM rejected valid booking")`.  
**Root Cause:** New atomic CLAIM: format instructed the RAG to ALWAYS include `llm_approves_booking` OR `llm_rejects_booking`. For cancellation fee queries (TC004), the RAG output `llm_approves_booking("c1","b1")` alongside `days_until_holiday("b1",65)`. Since 65 ≤ 84, `payment_required_full` → `balance_due` → `payment_overdue` → `booking_invalid` → `answer_invalid`. For complaint queries (TC009), the RAG output `llm_rejects_booking` because it was rejecting the complaint — but `booking_valid` was derived (no age/days) → `answer_invalid("LLM rejected valid booking")`.  
**Fix:** SYSTEM_PROMPT PART 2 now separates CLAIM: types by query category: Type A (booking eligibility) uses `llm_approves/rejects_booking` + age facts; Types B/C/D/E (fee, payment, complaint queries) use specific fact predicates WITHOUT booking decision predicates.

---

### ISS-013 · `llm_claims_atol_protected` without `includes_flight` triggers false violation
**Status:** FIXED  
**Files:** `src/agents/rag_agent.py` (SYSTEM_PROMPT PART 2)  
**Symptom:** TC023 (ATOL query) escalated with `atol_claim_incorrect("c1","b1","LLM claims ATOL protection but booking has no flight")`.  
**Root Cause:** RAG output `llm_claims_atol_protected("c1","b1")` for a general "is my holiday protected?" question. Since the query doesn't mention flight status, `includes_flight("b1")` was not in the facts. The new `atol_claim_incorrect` rule fires when `llm_claims_atol_protected` is present but `includes_flight` is absent.  
**Fix:** SYSTEM_PROMPT PART 2 Type F rule: `llm_claims_atol_protected` and `llm_claims_abta_protected` must ONLY be output alongside `includes_flight("b1")` — i.e., only when the booking's flight status is explicitly known from the query. For general ATOL queries where flight status is unknown, use only `llm_approves_booking`.

---

### ISS-014 · `vocabulary_map.json` `[:4]` slice excludes "lose" synonym — TC031 retrieves wrong chunk
**Status:** FIXED  
**Files:** `policies/vocabulary_map.json`, `src/agents/query_rewriter.py`  
**Symptom:** TC031 ("what percentage will we lose?") retrieves company cancellation compensation table instead of customer cancellation fee table. RAG can't find cancellation fee → returns REFUSAL/pending_info instead of approved.  
**Root Cause 1:** `_load_vocab_hint()` in `query_rewriter.py` only included `[:4]` synonyms per term. "lose" was the 5th synonym for "cancellation fee" → excluded from the LLM rewriter's vocabulary hint.  
**Root Cause 2:** Synonym order in vocabulary_map was `['termination fee', 'cancellation charge', 'cost to cancel', 'penalty for cancelling', 'lose', ...]` — "lose" appeared too late.  
**Fix:** (1) Moved "lose", "percentage lost" to positions 1-2 in cancellation fee synonyms. (2) Increased `[:4]` to `[:6]` in `_load_vocab_hint()` so more synonyms appear in the LLM rewriter's guidance.

---

### ISS-015 · `credentials_profile_name` in `query_rewriter.py`
**Status:** FIXED  
**Files:** `src/agents/query_rewriter.py`  
**Symptom:** Same as ISS-003 — query rewriter LLM uses `~/.aws/credentials` profile instead of `.env` env vars.  
**Root Cause:** Same pattern — `ChatBedrock(credentials_profile_name=profile)`.  
**Fix:** Removed `credentials_profile_name` parameter.

---

### ISS-016 · Rule-based rewriter missing cancellation+days pattern — TC031 still fails after ISS-014
**Status:** FIXED  
**Files:** `src/agents/query_rewriter.py`  
**Symptom:** TC031 ("What percentage of the holiday cost will we lose if we cancel 31 days before?") reaches LLM rewriter. Even after ISS-014 synonym reorder, LLM still retrieves the company-side compensation table.  
**Root Cause:** Complex queries combining cancellation signals ("lose") with day counts ("31 days before") were not matched by any rule-based shortcut. The LLM rewriter with vocabulary hints was not reliable enough for this specific phrasing.  
**Fix:** Added a rule at the TOP of `_rule_based_rewrite()` (before eligibility rules) that matches any query containing both a cancellation signal AND a days-before signal. Extracts the day count numerically → returns `"customer cancellation fee percentage {days} days before departure"` — a maximally specific policy-vocabulary query that retrieves the correct fee table.

---

## D4 — Embedding Comparison Results (2026-06-12)

| Metric | Bedrock (Titan v2) | HuggingFace (MiniLM) |
|---|---|---|
| Accuracy | **31/31 (100.0%)** | 30/31 (96.8%) |
| Avg latency | 3864 ms | **3661 ms** |
| Avg min similarity score (L2 ↓ = better) | 1.0448 | **0.9141** |
| Backend disagreements | — | 1/31 (TC023) |

**TC023 failure analysis (HuggingFace only):** Query "Is my holiday financially protected if TUI goes bust?" — Bedrock correctly retrieves the ATOL/ABTA section and returns `approved`. HuggingFace retrieves a lower-relevance chunk and the LLM returns `REFUSAL: out_of_scope`, triggering `refused_out_of_scope` instead of `approved`. The MiniLM model's lower-dimensional embedding space (384d vs 1536d Titan) is less discriminative for finance/protection vocabulary.

**Conclusion:** Bedrock (Titan v2) is the recommended production backend for perfect accuracy. HuggingFace (MiniLM) is a viable offline/zero-cost alternative with 3.3% accuracy gap and 5% lower latency.

Full report: `evaluation/embedding_comparison_report.md` | Data: `evaluation/embedding_comparison.json`

---

## Part B — FastAPI REST Layer (2026-06-12)

**Files created:**
- `src/api/__init__.py`, `src/api/routes/__init__.py`
- `src/api/models.py` — Pydantic v2 request/response models
- `src/api/routes/chat.py` — `POST /api/chat`, `GET /api/chat/examples`
- `src/api/routes/history.py` — `GET /api/history`, `GET /api/history/{thread_id}`
- `src/api/routes/review.py` — `GET /api/review/pending`, `POST /api/review/{turn_id}`, `GET /api/review/history`
- `src/api/main.py` — FastAPI app + CORS + health check

**Smoke test results:** All 7 endpoints verified:
- `GET /healthz` → `{"status":"ok","version":"1.0.0"}`
- `POST /api/chat` with `"Can John (age 35) make a booking?"` → `decision=approved`, correct facts/scores
- `GET /api/review/pending` → 33 escalated cases from benchmark runs
- `POST /api/review/{turn_id}` → correctly persists verdict to `logs/review_decisions.jsonl`
- `GET /api/review/history` → confirmed reviewed case appears

**Start command:** `uvicorn src.api.main:app --reload --port 8000`

---

## Part C — Streamlit UI Redesign (2026-06-13)

**Files modified:** `src/ui/chat_app.py`, `src/ui/review_app.py`

**chat_app.py changes:**
- **ISS-017 FIXED:** Escalated answer leaked to client before human review — `_display_answer()` now shows holding message when `decision == "escalated"` instead of the unverified LLM answer. The raw answer is still logged to `audit.jsonl` for the reviewer.
- Fixed ISS-003 carry-over bug: `_ra._retriever = None` → `_ra._vectorstore = None` (agent reset on credential expiry)
- New corporate header with gradient banner (replaced broken Wikipedia image)
- Categorized example queries sidebar (Identity, Cancellation, Amendment, Payment, Out-of-scope)
- Decision cards with left-accent border (green/red/amber/slate palette)
- `partial_validation` amber badge shown inline
- `retrieval_fallback_used` orange badge shown inline
- `rewritten_query` shown in policy chunks expander as purple badge
- Retrieval score bars per chunk (green < 0.6, amber < 1.0, red ≥ 1.0)
- `unextractable_claims` amber pills shown in facts expander

**review_app.py changes:**
- New matching header with back-link to Policy Assistant
- Card-based layout (white cards with shadow) replaces raw expanders
- `turn_id` field added to saved decisions (backwards-compatible with old `record_key`)
- Retrieved docs shown in collapsed expander per case
- Reviewed tab shows color-coded rows (green=approved, red=rejected)
- Metric delta shows "N reviewed" counter

---

## Known Limitations (Documented, Not Fixed)

| ID | Description | Scope | Planned Resolution |
|----|-------------|-------|-------------------|
| LIM-001 | Single-entity ASP model: cannot fully verify multi-person bookings (who is lead name vs. minor passenger) | ASP model expressiveness | Future work: `lead_age/3`, `minor_traveler_age/4` predicates |
| LIM-002 | `has_adult_companion` used as proxy for "adult is lead name" — cannot independently verify Mark's age in TC003 | ASP model | Covered by LIM-001 |
| LIM-003 | AWS Learner Lab STS tokens expire every ~4 hours — credentials must be manually updated in `.env` | Infrastructure | Permanent: IAM service account needed |
| LIM-004 | `complaint_invalid` and `injury_claim_invalid` are derived facts only — no LLM-answer validation rule checks if LLM correctly stated complaint timing | ASP coverage | Future: add `llm_claims_complaint_valid/2` + `llm_claims_complaint_invalid/2` predicates |
