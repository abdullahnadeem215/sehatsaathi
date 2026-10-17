"""Tests for Grounding Verification, Source Line Formatting, and Honest Handoff (FR-02, FR-03, FR-14, FR-15, UX-16, UX-28).
"""
import pytest
from backend.services.grounding_service import grounding_service, HONEST_HANDOFF_TEXT

SAMPLE_SUMMARY_LINES = [
    {"line_id": "L1", "text": "Patient was admitted for Type 2 Diabetes management and mild hypertension."},
    {"line_id": "L2", "text": "Take Tablet Metformin 500mg once daily in the morning after breakfast."},
    {"line_id": "L3", "text": "Take Tablet Amlodipine 5mg once daily at night after dinner."},
    {"line_id": "L4", "text": "Take Tablet Panadol 500mg as needed for body ache or fever, not exceeding two tablets per day."}
]


def test_valid_grounded_answer():
    is_grounded, final_answer, source_line, badge = grounding_service.verify_grounding(
        llm_answer="Take Metformin 500mg every morning after breakfast.",
        cited_line_ids=["L2"],
        confidence=0.95,
        summary_lines=SAMPLE_SUMMARY_LINES
    )
    assert is_grounded is True
    assert badge == "Certain"
    assert "Take Metformin 500mg" in final_answer
    assert source_line == "Your discharge summary says: Take Tablet Metformin 500mg once daily in the morning after breakfast."


def test_invalid_line_id_converts_to_handoff():
    # FR-03: If any ID is invalid, answer is not shown as grounded and converts to handoff
    is_grounded, final_answer, source_line, badge = grounding_service.verify_grounding(
        llm_answer="Invented medication dosage.",
        cited_line_ids=["L999"],
        confidence=0.95,
        summary_lines=SAMPLE_SUMMARY_LINES
    )
    assert is_grounded is False
    assert final_answer == HONEST_HANDOFF_TEXT
    assert source_line is None
    assert badge == "Unknown"


def test_missing_line_id_converts_to_handoff():
    # FR-03: If none is cited, converts to handoff
    is_grounded, final_answer, source_line, badge = grounding_service.verify_grounding(
        llm_answer="General knowledge advice without citation.",
        cited_line_ids=[],
        confidence=0.90,
        summary_lines=SAMPLE_SUMMARY_LINES
    )
    assert is_grounded is False
    assert final_answer == HONEST_HANDOFF_TEXT
    assert source_line is None
    assert badge == "Unknown"


def test_low_confidence_converts_to_handoff():
    # FR-14: If confidence < CONFIDENCE_THRESHOLD (0.6), converts to honest handoff
    is_grounded, final_answer, source_line, badge = grounding_service.verify_grounding(
        llm_answer="Maybe take Metformin?",
        cited_line_ids=["L2"],
        confidence=0.45,
        summary_lines=SAMPLE_SUMMARY_LINES
    )
    assert is_grounded is False
    assert final_answer == HONEST_HANDOFF_TEXT
    assert source_line is None
    assert badge == "Unknown"


def test_provider_failure_returns_handoff():
    # FR-15: Provider safety failure or timeout results in handoff, never an invented answer
    handoff = grounding_service.build_safety_failure_handoff(reason="Timeout exceeded")
    assert handoff["answer"] == HONEST_HANDOFF_TEXT
    assert handoff["ui_state"] == "handoff"
    assert handoff["confidence"] == 0.0
