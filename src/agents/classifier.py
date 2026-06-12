"""
Classifier Node — deterministic, no LLM call.

Reads the RAG agent's text output and checks for CLAIM:/REFUSAL: markers.
This is NOT semantic classification — it just reads explicit output markers
that the RAG agent was instructed to include via its system prompt.

Failure mode: both markers present simultaneously → classification_error=True
→ Decision node escalates. False escalation is always safer than false approval.
"""

from src.state import GuardrailsState
from src.telemetry import node, set_span_attrs
from src.pipeline_logger import log_classifier


@node("classifier")
def classifier_node(state: GuardrailsState) -> dict:
    """
    Classify the RAG Agent's output into one of three cases:
      - Clarification question: no CLAIM: or REFUSAL: lines
      - Final factual answer:   at least one CLAIM: line, no REFUSAL:
      - Out-of-scope refusal:   exactly one REFUSAL: line, no CLAIM:

    Reads:  state["llm_answer"]
    Writes: is_clarification, is_refusal, classification_error
    """
    answer = state.get("llm_answer", "")
    lines = [line.strip() for line in answer.splitlines()]

    has_claims = any(line.startswith("CLAIM:") for line in lines)
    has_refusal = any(line.startswith("REFUSAL:") for line in lines)

    log_classifier(
        not has_claims and not has_refusal,
        has_refusal and not has_claims,
        has_claims and has_refusal,
    )
    set_span_attrs({
        "classifier.has_claims": has_claims,
        "classifier.has_refusal": has_refusal,
        "classifier.answer_length": len(answer),
    })

    return {
        "is_clarification": not has_claims and not has_refusal,
        "is_refusal": has_refusal and not has_claims,
        "classification_error": has_claims and has_refusal,
    }
