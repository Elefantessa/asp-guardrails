"""
Phase 3.5 — Query Rewriting Agent

Bridges the vocabulary gap between user queries and policy text vocabulary.
Runs BEFORE the RAG agent so ChromaDB retrieval uses policy-aligned terms.

Two-tier strategy:
  1. Rule-based (zero latency): known patterns are replaced with a focused
     policy-vocabulary query instantly — no LLM call.
  2. LLM fallback (Haiku): if no rule matches, a cheap LLM rewrites the
     query guided by policy vocabulary hints.

This keeps latency minimal for common patterns while generalising to novel
queries that fall outside the hardcoded rules.
"""

import os
from dotenv import load_dotenv
from langchain_aws import ChatBedrock
from langchain_core.messages import HumanMessage, SystemMessage

from src.state import GuardrailsState
from src.telemetry import node, set_span_attrs

load_dotenv()

# ── Policy vocabulary hints for the LLM fallback ──────────────────────────────

_VOCAB_HINT = """
Key policy terms and their common user paraphrases:
- "adult" / "18 or older" / "lead name on the booking"
    ← user says: "age XX", "grown up", "main person", "lead booker"
- "accompanied by an adult" / "adult companion"
    ← user says: "with parent", "with adult", "with guardian", "with someone"
- "amendment fee" / "change treated as cancellation" / "29-day rule"
    ← user says: "change accommodation", "change hotel", "switch room", "swap room"
- "84 days" / "deposit" / "full payment when you book"
    ← user says: "pay in full", "full amount", "pay now", "do I need to pay everything"
- "28-day complaint deadline"
    ← user says: "complain", "make a complaint", "raise a complaint"
- "90-day injury claim deadline"
    ← user says: "personal injury", "accident claim", "compensation"
- "cancellation fee" / "percentage of holiday cost"
    ← user says: "cancel my holiday", "get a refund", "cancel booking"
"""

_REWRITE_SYSTEM = f"""You are a query normalisation assistant for a holiday booking policy system.

Your task: rewrite the user question into a short retrieval query (5–12 words)
using the exact vocabulary that appears in the policy document.

Policy vocabulary guide:
{_VOCAB_HINT}

Rules:
- Output ONLY the rewritten query. No explanation, no punctuation, no quotes.
- Use policy vocabulary (e.g. "lead name", "accompanied by adult", "amendment fee").
- Strip noisy identifiers: booking IDs, holiday codes, destination names.
- Keep numeric values that determine policy thresholds (ages, days).
- If the query is already in policy vocabulary, return it unchanged.
- If the query is unrelated to holiday booking, return it unchanged."""

# ── Singleton LLM — Haiku (cheap + fast; sufficient for short rewriting) ──────

_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        profile = os.getenv("AWS_PROFILE", "default")
        _llm = ChatBedrock(
            model_id=os.getenv(
                "BEDROCK_REWRITER_LLM",
                "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
            ),
            region_name=os.getenv("AWS_DEFAULT_REGION", "eu-central-1"),
            credentials_profile_name=profile,
            model_kwargs={
                "temperature": 0,
                "max_tokens": 64,
            },
        )
    return _llm


# ── Rule-based fast path ──────────────────────────────────────────────────────

def _rule_based_rewrite(query: str) -> str | None:
    """
    Return a focused policy-vocabulary query for known patterns.
    Returns None if no rule matches, signalling the LLM fallback.
    """
    q = query.lower()

    # Age / lead-name eligibility (e.g. "Can John (age 35) make a booking?")
    if any(p in q for p in ["make a booking", "can i book", "lead booker"]) and "age " in q:
        return "lead name must be adult age requirement booking eligibility"

    # Minor travelling with adult companion
    if any(p in q for p in ["accompanied", "with parent", "with adult"]) and \
       any(p in q for p in ["age ", "under 18", "minor", "child"]):
        return "minor under 18 accompanied adult companion travel"

    # Amendment / accommodation changes
    if any(p in q for p in ["change my accommodation", "change accommodation",
                              "change my hotel", "change my room"]):
        return "amendment fee accommodation change treated as cancellation 29 days before"

    # Payment / deposit deadlines
    if any(p in q for p in ["full amount", "full payment", "do i need to pay",
                              "pay now", "pay the full"]):
        return "deposit full payment 84 days when to pay balance booking"

    # Financial protection / insolvency (ATOL/ABTA) — keep exact vocabulary
    # so the RAG agent retrieves the ATOL/ABTA chunk rather than refuting.
    if any(p in q for p in ["financially protected", "goes bust", "goes bankrupt",
                              "insolvency", "atol", "abta", "financial protection"]):
        return "ATOL ABTA financial protection holiday booking insolvency"

    return None


# ── Node ──────────────────────────────────────────────────────────────────────

@node("query_rewriter")
def query_rewriter_node(state: GuardrailsState) -> dict:
    """
    Query Rewriting Agent.

    Reads:  state["messages"]     (extracts the user query from conversation)
    Writes: state["rewritten_query"]
    """
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    latest = user_messages[-1].content if user_messages else ""
    raw_query = (
        f"{user_messages[0].content} {latest}"
        if len(user_messages) > 1
        else latest
    )

    # Tier 1: rule-based — zero latency
    rule_result = _rule_based_rewrite(raw_query)
    if rule_result is not None:
        set_span_attrs({
            "query_rewriter.method": "rule",
            "query_rewriter.original": raw_query[:80],
            "query_rewriter.rewritten": rule_result,
        })
        return {"rewritten_query": rule_result}

    # Tier 2: LLM fallback — Haiku
    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=_REWRITE_SYSTEM),
        HumanMessage(content=raw_query),
    ])
    rewritten = response.content.strip()

    set_span_attrs({
        "query_rewriter.method": "llm",
        "query_rewriter.original": raw_query[:80],
        "query_rewriter.rewritten": rewritten[:80],
    })

    return {"rewritten_query": rewritten}
