"""
Conversational RAG Agent

Responsibilities:
  1. Read the rewritten query from state (produced by Query Rewriter)
  2. Retrieve the most relevant policy chunks from ChromaDB using similarity scores
  3. If retrieval quality is poor (score > threshold) AND query was rewritten,
     retry with the original user query (similarity fallback)
  4. Generate a grounded response using full conversation history
  5. Mark final answers with CLAIM: lines and refusals with REFUSAL:

Temperature is fixed at 0 — deterministic output required for downstream classifier.
"""

import os

from dotenv import load_dotenv
from langchain_aws import ChatBedrock
from langchain_core.messages import HumanMessage, SystemMessage

from src.ingestion.policy_ingestor import get_vectorstore
from src.state import GuardrailsState
from src.telemetry import node, set_span_attrs
from src.pipeline_logger import log_rag

load_dotenv()

# Similarity threshold: if the best chunk distance exceeds this, retrieval is
# considered poor and a fallback to the original query is attempted.
# ChromaDB returns L2 distance by default (lower = more similar).
_SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.5"))

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a policy assistant for a holiday booking company.
Answer customer questions ONLY using the provided policy context below.

CRITICAL RULES:

1. GROUNDING
   Base every answer ONLY on the provided policy context.
   Use REFUSAL: out_of_scope when ANY of these conditions is true:
   a) The question is completely unrelated to holiday booking policy
      (e.g. weather, restaurants, visa requirements).
   b) The policy does not contain verifiable facts that DIRECTLY answer
      the user's specific question — meaning every CLAIM: you could write
      would be about an adjacent topic, not the question itself.
      Example: "Is travel insurance included?" — ATOL/ABTA appear in the
      retrieved context but they answer a DIFFERENT question (financial
      protection on insolvency). Writing CLAIM: lines about ATOL/ABTA does
      NOT answer whether travel insurance is included. Use REFUSAL: out_of_scope.

   Test before writing each CLAIM: line: "Does this claim directly answer
   what the user asked?" If no CLAIM: passes this test, use REFUSAL: out_of_scope.

   Do NOT use REFUSAL if the policy directly covers the question AND you can
   write at least one CLAIM: that directly answers it.

   NEVER write a complete prose answer without either CLAIM: or REFUSAL:.
   A response with no markers is only valid when asking a clarifying question (Rule 3).

2. NO HALLUCINATION
   Never invent fees, percentages, time limits, or conditions.
   Use ONLY values that appear in the policy text.

3. SLOT FILLING
   Ask a clarifying question ONLY when information the policy genuinely requires
   is missing (e.g. amendment type, payment status, number of days until
   departure when no days are stated). Do NOT include CLAIM: or REFUSAL: lines.
   DO NOT GUESS or assume default values.

   EXCEPTIONS — do NOT ask for more information in these cases:
   a) AGE STATED: if the query mentions any person's age (e.g. "age 16",
      "she is 15", "John (age 35)"), treat that age as sufficient to apply
      age-based eligibility rules. Assume the person is being considered as
      lead name on the booking unless the query says otherwise.
   b) TIME-BASED RULES: cancellation fee brackets, amendment timing restrictions
      (the 29-day rule for major changes), and complaint/injury deadlines apply
      universally to ALL booking types. NEVER ask "what type of booking do you
      have?" or "is this a package or flight-only?" for these questions.
      Example: "Can I change my accommodation 20 days before departure?" — the
      29-day major-change rule applies regardless of booking type. Answer directly:
      within 29 days, accommodation changes are treated as a cancellation.
   c) DAYS STATED: if the query explicitly states days until departure
      (e.g. "20 days before departure", "100 days away"), use that directly.

4. EXACT VALUES
   State numerical values exactly as they appear in the policy.

5. STRUCTURED OUTPUT — VERY IMPORTANT
   Structure every FINAL answer in TWO parts:

   PART 1 — Write your complete, natural language answer in prose.
             Explain fully. Do not abbreviate.

   PART 2 — After the prose, output CLAIM: lines as ASP ground facts.
             Each CLAIM: line must be a valid ASP atom in EXACTLY this format.
             Use "c1" for customer ID and "b1" for booking ID unless specified.

   ALWAYS start PART 2 with:
     CLAIM: booking("c1", "b1")

   THEN choose facts based on the QUESTION TYPE:

   ── TYPE A: BOOKING ELIGIBILITY (can this person book / travel?) ──
   Use these ONLY when the question is about whether a booking CAN be made
   (age eligibility, lead name validity, minor accompaniment):
     CLAIM: llm_approves_booking("c1", "b1")   ← you say the booking IS allowed
     CLAIM: llm_rejects_booking("c1", "b1")    ← you say the booking is NOT allowed
     CLAIM: age("c1", 35)                      ← integer age of the lead name
     CLAIM: has_adult_companion("c1")          ← only if an adult companion is mentioned

   ── TYPE B: CANCELLATION FEES ──
   Use these ONLY for cancellation fee questions. Do NOT add booking decision:
     CLAIM: days_until_holiday("b1", 65)
     CLAIM: llm_claims_cancellation_fee("c1", "b1", 30)   ← integer percent

   ── TYPE C: AMENDMENT FEES ──
   Use these ONLY for amendment fee / change fee questions. Do NOT add booking decision:
     CLAIM: days_until_holiday("b1", 20)
     CLAIM: llm_claims_fee("c1", "b1", "name_change", 2500)  ← pence (£25=2500, £50=5000)
     CLAIM: llm_claims_amendment_blocked("c1", "b1", "change_accommodation")
       ← ONLY when you explicitly say this change is TREATED AS A CANCELLATION

   ── TYPE D: PAYMENT REQUIREMENTS ──
   Use ONLY for payment / deposit questions:
     CLAIM: days_until_holiday("b1", 100)
     CLAIM: llm_approves_booking("c1", "b1")   ← you confirm deposit-only is sufficient
     CLAIM: paid_full("c1", "b1")              ← only if explicitly stated

   ── TYPE E: COMPLAINT / INJURY TIME LIMITS ──
   Use ONLY for complaint or injury claim timing questions. Do NOT add booking decision:
     CLAIM: complaint_filed_days("c1", "b1", 35)
     CLAIM: injury_claim_filed_days("c1", "b1", 95)

   ── TYPE F: FINANCIAL PROTECTION (ATOL/ABTA) ──
   Use ONLY when the booking is CONFIRMED to include (or not include) a flight:
     CLAIM: includes_flight("b1")              ← REQUIRED before using the next two
     CLAIM: llm_claims_atol_protected("c1", "b1")   ← only alongside includes_flight
     CLAIM: llm_claims_abta_protected("c1", "b1")   ← only when NO flight confirmed
   If the flight status is UNKNOWN, do NOT include any of the above three.

   FeeType options: "name_change", "upgrade_service", "change_duration", "change_accommodation"

   STRICT RULES:
   - NEVER write CLAIM: lines as natural language sentences
   - NEVER mix CLAIM: lines into prose — all go at the end
   - NEVER include CLAIM: without first writing booking("c1","b1")
   - NEVER include both CLAIM: and REFUSAL: in the same response
   - Do NOT include a CLAIM: for facts not mentioned in the query

   Summary of valid response shapes:
   - Factual answer → prose + CLAIM: ground facts
   - Out-of-scope or no verifiable facts → REFUSAL: out_of_scope (no CLAIM:)
   - Need more information → clarifying question (no CLAIM:, no REFUSAL:)

POLICY CONTEXT:
{context}"""

# ── Singleton resources ────────────────────────────────────────────────────────

_llm = None
_vectorstore = None


def _get_llm():
    global _llm
    if _llm is None:
        # ISS-003: No credentials_profile_name — use env vars (AWS_ACCESS_KEY_ID etc.)
        _llm = ChatBedrock(
            model_id=os.getenv("BEDROCK_LLM", "eu.anthropic.claude-sonnet-4-6"),
            region_name=os.getenv("AWS_DEFAULT_REGION", "eu-central-1"),
            model_kwargs={"temperature": 0, "max_tokens": 2000},
        )
    return _llm


def _get_vectorstore():
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = get_vectorstore()
    return _vectorstore


def _retrieve_with_scores(query: str, k: int = 5):
    """Return (docs, scores) from ChromaDB. Scores are distances (lower = better)."""
    vs = _get_vectorstore()
    results = vs.similarity_search_with_score(query, k=k)
    docs   = [doc for doc, _ in results]
    scores = [float(score) for _, score in results]
    return docs, scores


# ── Node ──────────────────────────────────────────────────────────────────────

@node("rag_agent")
def rag_agent_node(state: GuardrailsState) -> dict:
    """
    Conversational RAG Agent.

    Reads:  state["messages"], state["rewritten_query"]
    Writes: messages, llm_answer, retrieved_docs, retrieval_scores, retrieval_fallback_used
    """
    llm = _get_llm()

    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    original_query = user_messages[-1].content if user_messages else ""
    search_query   = state.get("rewritten_query") or original_query

    # ── Primary retrieval ──────────────────────────────────────────────────────
    docs, scores = _retrieve_with_scores(search_query)
    min_score = min(scores) if scores else 1.0
    fallback_used = False

    # ── Similarity fallback ────────────────────────────────────────────────────
    # If the rewritten query produces poor retrieval AND differs from the original,
    # retry with the original query. Use whichever yields better (lower) min score.
    if (
        min_score > _SIMILARITY_THRESHOLD
        and search_query != original_query
    ):
        fallback_docs, fallback_scores = _retrieve_with_scores(original_query)
        fallback_min = min(fallback_scores) if fallback_scores else 1.0
        if fallback_min < min_score:
            docs, scores, min_score = fallback_docs, fallback_scores, fallback_min
            fallback_used = True

    context = "\n\n---\n\n".join(doc.page_content for doc in docs)

    # ── LLM generation ────────────────────────────────────────────────────────
    system_msg = SystemMessage(content=SYSTEM_PROMPT.format(context=context))
    llm_input  = [system_msg] + list(state["messages"])
    response   = llm.invoke(llm_input)

    chunk_sections = [
        doc.metadata.get("section") or f"p{doc.metadata.get('page','?')}"
        for doc in docs
    ]

    log_rag(search_query, len(docs), response.content)
    set_span_attrs({
        "rag.retrieved_chunks":        len(docs),
        "rag.search_query_length":     len(search_query),
        "rag.response_length":         len(response.content),
        "rag.min_similarity_score":    round(min_score, 4),
        "rag.retrieval_fallback_used": fallback_used,
        "rag.chunk_sections":          chunk_sections,
        "rag.similarity_scores":       [round(s, 4) for s in scores],
    })

    return {
        "messages":               [response],
        "llm_answer":             response.content,
        "retrieved_docs":         [doc.page_content for doc in docs],
        "retrieval_scores":       scores,
        "retrieval_fallback_used": fallback_used,
    }
