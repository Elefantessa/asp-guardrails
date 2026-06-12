"""
Phase 4 — LangGraph Orchestration

Builds the multi-agent guardrails graph:

    START
      │
    Query Rewriter ──→ RAG Agent ──→ Classifier
                                         │
                                 ┌───────┴───────┐
                            clarif/refusal/err   final answer
                                 │               │
                                 │          Fact Extractor
                                 │               │
                                 │          ASP Validator
                                 │               │
                                 └───────┬───────┘
                                      Decision
                                         │
                                        END

PostgresSaver is used when USE_POSTGRES_CHECKPOINTER=true in .env.
Otherwise, MemorySaver is used (development default).
"""

import os

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.agents.asp_validator import asp_validator_node
from src.agents.classifier import classifier_node
from src.agents.decision import decision_node
from src.agents.fact_extractor import fact_extraction_agent_node
from src.agents.query_rewriter import query_rewriter_node
from src.agents.rag_agent import rag_agent_node
from src.state import GuardrailsState

load_dotenv()


def _route_after_classification(state: GuardrailsState) -> str:
    """
    Conditional edge: skip validation for clarifications, refusals, and errors.
    Only final factual answers (CLAIM: lines present) go through the validator.
    """
    if (
        state.get("is_clarification", False)
        or state.get("is_refusal", False)
        or state.get("classification_error", False)
    ):
        return "skip_validation"
    return "needs_validation"


def build_graph(checkpointer=None):
    """
    Compile and return the guardrails graph.

    Args:
        checkpointer: Override the default checkpointer.
                      Defaults to PostgresSaver (if configured) or MemorySaver.

    Returns:
        Compiled LangGraph ready for graph.invoke().
    """
    workflow = StateGraph(GuardrailsState)

    # Register nodes
    workflow.add_node("query_rewriter", query_rewriter_node)
    workflow.add_node("rag_agent", rag_agent_node)
    workflow.add_node("classifier", classifier_node)
    workflow.add_node("fact_extractor", fact_extraction_agent_node)
    workflow.add_node("asp_validator", asp_validator_node)
    workflow.add_node("router", decision_node)

    # Wire edges
    workflow.add_edge(START, "query_rewriter")
    workflow.add_edge("query_rewriter", "rag_agent")
    workflow.add_edge("rag_agent", "classifier")
    workflow.add_conditional_edges(
        "classifier",
        _route_after_classification,
        {
            "needs_validation": "fact_extractor",
            "skip_validation": "router",
        },
    )
    workflow.add_edge("fact_extractor", "asp_validator")
    workflow.add_edge("asp_validator", "router")
    workflow.add_edge("router", END)

    # Attach checkpointer
    if checkpointer is None:
        use_pg = os.getenv("USE_POSTGRES_CHECKPOINTER", "false").lower() == "true"
        if use_pg:
            from langgraph.checkpoint.postgres import PostgresSaver
            db_url = os.getenv("DATABASE_URL")
            checkpointer = PostgresSaver.from_conn_string(db_url)
            checkpointer.setup()
        else:
            checkpointer = MemorySaver()

    return workflow.compile(checkpointer=checkpointer)
