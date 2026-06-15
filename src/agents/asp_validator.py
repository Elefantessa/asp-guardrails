"""
Phase 3 — ASP Validator Node

Symbolic verification: runs Clingo against the encoded policy rules
and checks whether the LLM's extracted claims contain any violations.

This is the formal guarantee component — deterministic and decidable.
No LLM is involved here.

Clingo API note (5.8.0):
  Use m.symbols(shown=True) to get #show-selected atoms,
  or m.symbols(atoms=True) to get all derived atoms.
"""

import clingo
from src.state import GuardrailsState
from src.telemetry import node, set_span_attrs
from src.pipeline_logger import log_asp

POLICY_FILE = "policies/holiday_policy.lp"

# LLM-answer-level violation predicates defined in holiday_policy.lp.
# ISS-005: Only include atoms that represent a WRONG LLM answer, NOT intermediate
# derived facts (booking_invalid, lead_name_invalid, complaint_invalid, etc.).
# Those intermediate facts are ASP-internal computations used by the validation
# layer — they fire correctly even when the LLM answer is right (e.g. TC002:
# LLM correctly refuses a minor booking → lead_name_invalid fires but that is
# expected, not a guardrail violation).
VIOLATION_PREFIXES = (
    "answer_invalid",                  # LLM approved invalid booking OR rejected valid booking
    "cancellation_claim_incorrect",    # LLM quoted wrong cancellation percentage
    "fee_claim_incorrect",             # LLM quoted wrong amendment fee
    "atol_claim_incorrect",            # LLM wrongly claimed ATOL protection (no flight in booking)
    "abta_claim_incorrect",            # LLM wrongly claimed ABTA protection (flight present)
    "amendment_assessment_incorrect",  # LLM wrongly said amendment is blocked/allowed
)


@node("asp_validator")
def asp_validator_node(state: GuardrailsState) -> dict:
    """
    Validate extracted facts against the ASP-encoded policy.

    Reads:  state["extracted_facts"]
    Writes: validation_passed, violations, derived_facts
    """
    facts   = state.get("extracted_facts", [])
    claims  = state.get("extracted_claims", [])

    if not facts:
        if claims:
            # Claims exist but none map to the predicate vocabulary.
            # This means the answer is qualitative/informational (e.g. booking
            # types, ATOL description) — outside ASP coverage, not provably wrong.
            # Approve rather than escalate: absence of verifiable facts ≠ error.
            log_asp(True, [], [])
            return {
                "validation_passed": True,
                "violations": [],
                "derived_facts": ["asp_coverage: unverifiable (qualitative claims)"],
            }
        # No claims at all — something unexpected, escalate.
        return {
            "validation_passed": False,
            "violations": ["No facts extracted from LLM answer — cannot validate"],
            "derived_facts": [],
        }

    try:
        with open(POLICY_FILE) as f:
            policy_rules = f.read()
    except FileNotFoundError:
        return {
            "validation_passed": False,
            "violations": [f"Policy file not found: {POLICY_FILE}"],
            "derived_facts": [],
        }

    program = (
        policy_rules
        + "\n\n% ═══ Facts extracted from LLM answer ═══\n"
        + "\n".join(facts)
    )

    ctl = clingo.Control(["--warn=none"])
    ctl.add("base", [], program)

    try:
        ctl.ground([("base", [])])
    except RuntimeError as e:
        return {
            "validation_passed": False,
            "violations": [f"ASP grounding error: {e}"],
            "derived_facts": [],
        }

    violations: list[str] = []
    derived: list[str] = []

    def on_model(model):
        for atom in model.symbols(shown=True):
            s = str(atom)
            if any(s.startswith(p) for p in VIOLATION_PREFIXES):
                violations.append(s)
            else:
                derived.append(s)

    ctl.solve(on_model=on_model)

    passed = len(violations) == 0
    log_asp(passed, violations, derived)
    set_span_attrs({
        "asp.validation_passed": passed,
        "asp.violations_count": len(violations),
        "asp.derived_facts_count": len(derived),
        "asp.facts_input_count": len(facts),
    })

    return {
        "validation_passed": passed,
        "violations": violations,
        "derived_facts": derived,
    }
