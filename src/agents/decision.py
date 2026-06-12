"""
Decision Node — deterministic, no LLM call.

Maps the accumulated state flags to a final routing decision.
Priority order (top = highest priority):

  1. classification_error → escalated  (conflicting output format)
  2. is_clarification     → pending_info
  3. is_refusal           → refused_out_of_scope
  4. validation_passed    → approved
  5. default              → escalated  (validation failed or no facts)
"""

from src.state import GuardrailsState
from src.telemetry import node, set_span_attrs
from src.pipeline_logger import log_decision


@node("router")
def decision_node(state: GuardrailsState) -> dict:
    """
    Set the final decision based on upstream node outputs.

    Reads:  is_clarification, is_refusal, classification_error,
            validation_passed, violations
    Writes: decision
    """
    if state.get("classification_error", False):
        decision = "escalated"
    elif state.get("is_clarification", False):
        decision = "pending_info"
    elif state.get("is_refusal", False):
        decision = "refused_out_of_scope"
    elif state.get("validation_passed", False):
        decision = "approved"
    else:
        decision = "escalated"

    log_decision(decision)
    set_span_attrs({
        "decision.result": decision,
        "decision.violations_count": len(state.get("violations", [])),
    })
    return {"decision": decision}
