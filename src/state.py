from typing import Annotated, Literal, Sequence
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class GuardrailsState(TypedDict):
    """
    Shared state passed between all LangGraph nodes.

    The 'messages' field uses add_messages to APPEND rather than replace,
    which is what enables multi-turn conversation memory across graph.invoke()
    calls with the same thread_id.
    """

    # ── Conversation (RAG Agent) ──────────────────────────────────────
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # ── Query Rewriter outputs ────────────────────────────────────────
    rewritten_query: str        # Policy-vocabulary retrieval query (rule-based or LLM)

    # ── RAG Agent outputs ─────────────────────────────────────────────
    retrieved_docs: list[str]   # Top-K policy chunks retrieved this turn
    llm_answer: str             # Raw text response from the LLM

    # ── Classifier outputs ────────────────────────────────────────────
    is_clarification: bool      # No CLAIM/REFUSAL marker → LLM asked for info
    is_refusal: bool            # REFUSAL: marker → out-of-scope question
    classification_error: bool  # Both CLAIM and REFUSAL present → escalate

    # ── Fact Extraction Agent outputs ─────────────────────────────────
    extracted_claims: list[str] # Raw "CLAIM:" lines from LLM answer
    extracted_facts: list[str]  # Validated ASP atoms (e.g. days_until_holiday("b1",65).)

    # ── ASP Validator outputs ─────────────────────────────────────────
    validation_passed: bool
    violations: list[str]       # Violation atoms (cancellation_claim_incorrect, etc.)
    derived_facts: list[str]    # All atoms in the Clingo answer set

    # ── Final decision ────────────────────────────────────────────────
    decision: Literal[
        "pending_info",          # LLM asked for more info; return clarification to user
        "refused_out_of_scope",  # Out-of-policy question; no ASP needed
        "approved",              # ASP verified; safe to show answer
        "escalated",             # Contradiction or syntax error; human review required
        "error",                 # Unexpected graph state
    ]
