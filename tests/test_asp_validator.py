"""
Tests for the ASP validator node.
No Bedrock calls — only Clingo, which is installed in the venv.
"""
import pytest
from src.agents.asp_validator import asp_validator_node


def validate(facts: list[str]) -> dict:
    return asp_validator_node({"extracted_facts": facts})


# ── Cancellation fee brackets ──────────────────────────────────────────────────

@pytest.mark.parametrize("days,expected_pct", [
    (100, 0), (70, 0),
    (69, 30), (65, 30), (63, 30),
    (62, 50), (49, 50),
    (48, 70), (29, 70),
    (28, 90), (15, 90),
    (14, 100), (1, 100),
])
def test_cancellation_brackets(days, expected_pct):
    facts = [
        'customer("c1").',
        'booking("c1", "b1").',
        f'days_until_holiday("b1", {days}).',
        f'llm_claims_cancellation_fee("c1", "b1", {expected_pct}).',
    ]
    result = validate(facts)
    assert result["validation_passed"] is True
    assert result["violations"] == []


def test_correct_fee_approved():
    """LLM claims 30% at 65 days — correct."""
    facts = [
        'customer("c1").',
        'booking("c1", "b1").',
        'days_until_holiday("b1", 65).',
        'llm_claims_cancellation_fee("c1", "b1", 30).',
    ]
    result = validate(facts)
    assert result["validation_passed"] is True


def test_wrong_fee_escalated():
    """LLM claims 50% at 65 days — hallucination, should fail."""
    facts = [
        'customer("c1").',
        'booking("c1", "b1").',
        'days_until_holiday("b1", 65).',
        'llm_claims_cancellation_fee("c1", "b1", 50).',
    ]
    result = validate(facts)
    assert result["validation_passed"] is False
    assert any("cancellation_claim_incorrect" in v for v in result["violations"])


# ── Booking validity ───────────────────────────────────────────────────────────

def test_adult_booking_approved():
    facts = [
        'customer("c1").',
        'booking("c1", "b1").',
        'age("c1", 35).',
        'days_until_holiday("b1", 107).',
        'llm_approves_booking("c1", "b1").',
    ]
    result = validate(facts)
    assert result["validation_passed"] is True


def test_no_facts_escalated():
    result = validate([])
    assert result["validation_passed"] is False
    assert result["violations"] != []
