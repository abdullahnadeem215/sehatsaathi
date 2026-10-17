"""Tests for Deterministic Red-Flag Detection and Emergency Escalation (FR-12, FR-13, UX-27).
"""
import pytest
from backend.services.safety_service import safety_service


def test_red_flag_chest_pain():
    phrases = [
        "I have severe chest pain right now",
        "There is heavy chest pressure and pain radiating to arm",
        "I feel sharp chest pain in my heart"
    ]
    for p in phrases:
        is_flag, details = safety_service.check_red_flag(p)
        assert is_flag is True, f"Failed to detect red flag in: {p}"
        assert details["category"] == "chest_pain"
        assert details["severity"] == "CRITICAL"


def test_red_flag_breathlessness():
    phrases = [
        "I cannot breathe properly and feel like I am choking",
        "Severe shortness of breath since morning",
        "The patient is breathless and gasping for air"
    ]
    for p in phrases:
        is_flag, details = safety_service.check_red_flag(p)
        assert is_flag is True, f"Failed to detect red flag in: {p}"
        assert details["category"] == "breathlessness"


def test_red_flag_fainting():
    phrases = [
        "I felt severe dizziness and fainted on the floor",
        "The patient passed out a minute ago",
        "He is unconscious and collapsed"
    ]
    for p in phrases:
        is_flag, details = safety_service.check_red_flag(p)
        assert is_flag is True, f"Failed to detect red flag in: {p}"
        assert details["category"] == "fainting"


def test_red_flag_severe_bleeding():
    phrases = [
        "There is severe bleeding from the surgery cut",
        "Blood is gushing from the wound and bleeding won't stop"
    ]
    for p in phrases:
        is_flag, details = safety_service.check_red_flag(p)
        assert is_flag is True, f"Failed to detect red flag in: {p}"
        assert details["category"] == "severe_bleeding"


def test_red_flag_stroke_weakness():
    phrases = [
        "I think I am having a stroke, my arm has sudden weakness",
        "Sudden numbness on one side and facial drooping",
        "Cannot move my arm and slurred speech"
    ]
    for p in phrases:
        is_flag, details = safety_service.check_red_flag(p)
        assert is_flag is True, f"Failed to detect red flag in: {p}"
        assert details["category"] == "sudden_weakness"


def test_emergency_response_construction_with_and_without_caregivers():
    # With caregivers
    resp_with = safety_service.build_emergency_response(
        transcript="Severe chest pain",
        matched_details={"category": "chest_pain", "description": "Chest pain / heart attack"},
        has_linked_caregivers=True
    )
    assert resp_with["ui_state"] == "emergency"
    assert "Your family has been alerted immediately" in resp_with["answer"]
    assert resp_with["is_emergency"] is True

    # Without caregivers
    resp_without = safety_service.build_emergency_response(
        transcript="Severe chest pain",
        matched_details={"category": "chest_pain", "description": "Chest pain / heart attack"},
        has_linked_caregivers=False
    )
    assert resp_without["ui_state"] == "emergency"
    assert "No family member is linked yet" in resp_without["answer"]
