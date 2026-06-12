"""Tests for the classifier node — fully deterministic, no LLM needed."""
import pytest
from src.agents.classifier import classifier_node


def classify(answer: str) -> dict:
    return classifier_node({"llm_answer": answer, "messages": []})


def test_claim_lines_detected():
    r = classify("The fee is 30%.\nCLAIM: Cancellation fee is 30% at 65 days.")
    assert r["is_clarification"] is False
    assert r["is_refusal"] is False
    assert r["classification_error"] is False


def test_refusal_detected():
    r = classify("That is not covered.\nREFUSAL: out_of_scope")
    assert r["is_refusal"] is True
    assert r["is_clarification"] is False
    assert r["classification_error"] is False


def test_no_markers_is_clarification():
    r = classify("How many days until your departure?")
    assert r["is_clarification"] is True
    assert r["is_refusal"] is False
    assert r["classification_error"] is False


def test_both_markers_is_error():
    r = classify("CLAIM: Something.\nREFUSAL: out_of_scope")
    assert r["classification_error"] is True


def test_empty_answer_is_clarification():
    r = classify("")
    assert r["is_clarification"] is True
