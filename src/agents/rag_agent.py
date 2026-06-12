"""
Phase 3 — Conversational RAG Agent (Agent 1)

The user-facing LLM agent. Responsibilities:
  1. Retrieve the most relevant policy chunks from ChromaDB
  2. Generate a grounded response using full conversation history
  3. Ask for missing information (slot detection) when needed
  4. Mark final answers with CLAIM: lines
  5. Mark out-of-scope refusals with REFUSAL: line

Temperature is fixed at 0 — deterministic output is required for the
downstream classifier to rely on CLAIM:/REFUSAL: markers reliably.
"""

import os

from dotenv import load_dotenv
from langchain_aws import BedrockEmbeddings, ChatBedrock
from langchain_community.vectorstores import Chroma
from langchain_core.messages import HumanMessage, SystemMessage

from src.state import GuardrailsState
from src.telemetry import node, set_span_attrs
from src.pipeline_logger import log_rag

load_dotenv()

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

   PART 2 — After the prose, on separate lines, list each specific
             factual claim using "CLAIM: " prefix. Example:

       The cancellation fee depends on how far in advance you cancel.
       For 65 days before departure, the fee is 30%.

       CLAIM: The cancellation fee is 30% for cancellations 63-69 days before departure.
       CLAIM: 65 days falls within the 63-69 day bracket.

   NEVER mix CLAIM: lines into the middle of your prose.
   NEVER include both CLAIM: and REFUSAL: in the same response.
   CLAIM: is for factual policy data (fees, dates, rules, ages).
   Do NOT add CLAIM: for general descriptions or lists of names.

   Summary of valid response shapes:
   - Factual answer → prose + one or more CLAIM: lines
   - Out-of-scope or no verifiable facts → REFUSAL: out_of_scope (no CLAIM:)
   - Need more information → clarifying question (no CLAIM:, no REFUSAL:)

POLICY CONTEXT:
{context}"""

# ── Singleton resources ────────────────────────────────────────────────────────

_llm = None
_retriever = None


def _get_llm():
    global _llm
    if _llm is None:
        profile = os.getenv("AWS_PROFILE", "default")
        _llm = ChatBedrock(
            model_id=os.getenv("BEDROCK_LLM",
                               "eu.anthropic.claude-sonnet-4-6"),
            region_name=os.getenv("AWS_DEFAULT_REGION", "eu-central-1"),
            credentials_profile_name=profile,
            model_kwargs={
                "temperature": 0,
                "max_tokens": 2000,
            },
        )
    return _llm


def _get_retriever():
    global _retriever
    if _retriever is None:
        persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
        chroma_path = f"{persist_dir}/holiday_policy"
        profile = os.getenv("AWS_PROFILE", "default")
        embeddings = BedrockEmbeddings(
            model_id=os.getenv("BEDROCK_EMBEDDINGS",
                               "amazon.titan-embed-text-v2:0"),
            region_name=os.getenv("AWS_DEFAULT_REGION", "eu-central-1"),
            credentials_profile_name=profile,
        )
        vectorstore = Chroma(
            collection_name="holiday_policy",
            embedding_function=embeddings,
            persist_directory=chroma_path,
        )
        _retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
    return _retriever


# ── Query augmentation ────────────────────────────────────────────────────────

def _augment_query(query: str) -> str:
    """
    Return a focused policy-vocabulary retrieval query that bridges the gap
    between natural-language queries and the vocabulary in the policy PDF.

    When specific patterns are detected the full user query is replaced with
    a clean concept query so noisy details (booking IDs, specific numbers)
    do not drown out the semantic signal.  No LLM call — zero latency.
    """
    q = query.lower()

    # Age / lead-name eligibility (e.g. "Can John (age 35) make a booking?")
    # Replace full query — specific IDs like "holiday ID B001" add retrieval noise.
    if any(p in q for p in ["make a booking", "can i book", "lead booker"]) and "age " in q:
        return "lead name must be adult age requirement booking eligibility"

    # Minor travelling with adult companion
    if any(p in q for p in ["accompanied", "with parent", "with adult"]) and \
       any(p in q for p in ["age ", "under 18", "minor", "child"]):
        return "minor under 18 accompanied adult companion travel"

    # Amendment / accommodation changes (e.g. "change my accommodation 20 days before")
    # Routes to the amendment fee table chunk, not the "company changes" chunks.
    if any(p in q for p in ["change my accommodation", "change accommodation",
                              "change my hotel", "change my room"]):
        return "amendment fee accommodation change treated as cancellation 29 days before"

    # Payment / deposit deadlines (e.g. "full amount … 100 days away")
    # Payment rule chunk is PDF-encoded; this maximises recall from related chunks.
    if any(p in q for p in ["full amount", "full payment", "do i need to pay",
                              "pay now", "pay the full"]):
        return "deposit full payment 84 days when to pay balance booking"

    return query


# ── Node ──────────────────────────────────────────────────────────────────────

@node("rag_agent")
def rag_agent_node(state: GuardrailsState) -> dict:
    """
    Conversational RAG Agent.

    Reads:  state["messages"]  (full conversation history via add_messages)
    Writes: messages, llm_answer, retrieved_docs
    """
    llm = _get_llm()
    retriever = _get_retriever()

    # Build search query: combine original question with latest reply
    # so follow-up turns ("65 days") find the right policy chunks.
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    latest = user_messages[-1].content if user_messages else ""
    raw_query = (
        f"{user_messages[0].content} {latest}"
        if len(user_messages) > 1
        else latest
    )
    search_query = _augment_query(raw_query)

    # Retrieve top-5 policy chunks
    docs = retriever.invoke(search_query)
    context = "\n\n---\n\n".join(doc.page_content for doc in docs)

    # Construct LLM input: system prompt + full conversation history
    system_msg = SystemMessage(content=SYSTEM_PROMPT.format(context=context))
    llm_input = [system_msg] + list(state["messages"])

    response = llm.invoke(llm_input)

    log_rag(search_query, len(docs), response.content)
    set_span_attrs({
        "rag.retrieved_chunks": len(docs),
        "rag.search_query_length": len(search_query),
        "rag.response_length": len(response.content),
    })

    return {
        "messages": [response],           # add_messages reducer appends
        "llm_answer": response.content,
        "retrieved_docs": [doc.page_content for doc in docs],
    }
