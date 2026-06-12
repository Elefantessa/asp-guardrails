"""
Phase 3 — Fact Extraction Agent (Agent 2)

Converts CLAIM: lines from the RAG agent's output into valid ASP atoms.
Uses a separate Bedrock call with a constrained output prompt — the model
is instructed to output ONLY ASP facts and nothing else.

Separation from Agent 1 is intentional:
  - This agent is stateless (doesn't need conversation history)
  - Optimised for structured output, not natural language
  - Lower max_tokens → cheaper and faster
  - Can be unit-tested independently with mock LLM
"""

import os
import re

from dotenv import load_dotenv
from langchain_aws import ChatBedrock
from langchain_core.messages import HumanMessage

from src.state import GuardrailsState
from src.telemetry import node, set_span_attrs
from src.pipeline_logger import log_extractor

load_dotenv()

# ── Prompt ────────────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """Convert these natural language claims into ASP facts for the Clingo solver.

USE ONLY THESE PREDICATES:

  customer(CustID).
  booking(CustID, BookID).
  age(CustID, Age).
  has_adult_companion(CustID).
  days_until_holiday(BookID, Days).
  paid_full(CustID, BookID).
  includes_flight(BookID).
  complaint_filed_days(CustID, BookID, Days).
  injury_claim_filed_days(CustID, BookID, Days).
  llm_approves_booking(CustID, BookID).
  llm_rejects_booking(CustID, BookID).
  llm_claims_cancellation_fee(CustID, BookID, Percent).
  llm_claims_fee(CustID, BookID, FeeType, AmountPence).

FORMATTING RULES:
1. One fact per line, ending with a period.
2. Use "c1" for customer ID and "b1" for booking ID unless the claims
   mention specific IDs.
3. Money values must be in pence (£25 = 2500, £50 = 5000).
4. Percentages must be integers (30, not 0.3).
5. FeeType options: "name_change", "upgrade_service",
   "change_duration", "change_accommodation".

OUTPUT CONSTRAINT:
- Output ONLY valid ASP ground facts, nothing else.
- No comments, no explanations, no markdown formatting, no backticks.
- ALL arguments must be GROUND (quoted strings or integers). NEVER use variable
  names like CustID, BookID, Age, Days as arguments — those are placeholders,
  not valid facts. Use "c1" and "b1" as default IDs.
- If NO claim can be mapped to any available predicate, output exactly: NO_FACTS

CLAIMS TO CONVERT:
{claims}

ASP FACTS:"""

# Ground ASP fact: lowercase predicate, args must be quoted strings or integers only.
# Rejects variable-style arguments like CustID, BookID (uppercase start).
FACT_PATTERN = re.compile(
    r'^[a-z][a-z_]*\('          # predicate name (lowercase)
    r'("[^"]*"|\d+)'             # first arg: "string" or integer
    r'(,\s*("[^"]*"|\d+))*'      # optional further args
    r'\)\.$'                     # closing
)

# ── Singleton LLM ─────────────────────────────────────────────────────────────

_llm = None


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
                "max_tokens": 800,
            },
        )
    return _llm


# ── Node ──────────────────────────────────────────────────────────────────────

@node("fact_extractor")
def fact_extraction_agent_node(state: GuardrailsState) -> dict:
    """
    Convert CLAIM: lines to ASP atoms.

    Reads:  state["llm_answer"]
    Writes: extracted_claims, extracted_facts
    """
    answer = state.get("llm_answer", "")

    # Parse CLAIM: lines from the RAG agent's response
    claims = [
        line.strip()[len("CLAIM:"):].strip()
        for line in answer.splitlines()
        if line.strip().startswith("CLAIM:")
    ]

    if not claims:
        return {"extracted_claims": [], "extracted_facts": []}

    llm = _get_llm()
    prompt = EXTRACTION_PROMPT.format(
        claims="\n".join(f"- {c}" for c in claims)
    )
    response = llm.invoke([HumanMessage(content=prompt)])

    # Parse and validate: keep only lines that match ASP fact syntax
    facts = []
    for line in response.content.strip().splitlines():
        line = line.strip().strip("`")  # strip markdown backticks if any
        if FACT_PATTERN.match(line):
            facts.append(line)

    log_extractor(claims, facts)
    set_span_attrs({
        "extractor.claims_count": len(claims),
        "extractor.valid_facts_count": len(facts),
        "extractor.llm_output_length": len(response.content),
    })

    return {
        "extracted_claims": claims,
        "extracted_facts": facts,
    }
