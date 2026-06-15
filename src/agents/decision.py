"""
Decision Node — deterministic, no LLM call.

Maps the accumulated state flags to a final routing decision.
Priority order (top = highest priority):

  1. classification_error  → escalated  (conflicting output format)
  2. is_clarification      → pending_info
  3. is_refusal            → refused_out_of_scope
  4. validation_passed=True AND partial_validation=False → approved
  5. validation_passed=True AND partial_validation=True  → escalated
     (ISS-004: some claims could not be mapped to predicates — symbolic check
      is incomplete, human review required. Proper fix: atomic CLAIM: format
      in rag_agent.py eliminates spurious partial_validation for validatable
      claims, so this escalation only fires for genuinely unvalidatable cases.)
  6. default               → escalated  (ASP found violations or no validation)
"""

from src.state import GuardrailsState
from src.telemetry import node, set_span_attrs
from src.pipeline_logger import log_decision


@node("router")
def decision_node(state: GuardrailsState) -> dict:
    """
    Set the final decision based on upstream node outputs.

    Reads:  is_clarification, is_refusal, classification_error,
            validation_passed, partial_validation, violations
    Writes: decision
    """
    if state.get("classification_error", False):
        decision = "escalated"
    elif state.get("is_clarification", False):
        decision = "pending_info"
    elif state.get("is_refusal", False):
        decision = "refused_out_of_scope"
    elif state.get("validation_passed", False):
        # ISS-004: partial_validation=True means at least one CLAIM: line could
        # not be mapped to any known predicate. The ASP check is incomplete —
        # escalate so a human reviewer can verify what the symbolic layer missed.
        if state.get("partial_validation", False):
            decision = "escalated"
        else:
            decision = "approved"
    else:
        decision = "escalated"

    log_decision(decision)
    set_span_attrs({
        "decision.result":            decision,
        "decision.violations_count":  len(state.get("violations", [])),
        "decision.partial_validation": state.get("partial_validation", False),
        "decision.fallback_used":     state.get("retrieval_fallback_used", False),
    })
    return {"decision": decision}
