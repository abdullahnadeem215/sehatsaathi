"""Deterministic safety and red-flag escalation service.
Enforces SRS FR-12, FR-13, and UX-27 (English-only edition).
"""
import os
import re
import json
from typing import Tuple, Optional, Dict, Any, List


class SafetyService:
    def __init__(self, red_flags_path: Optional[str] = None):
        if not red_flags_path:
            red_flags_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "data", "red_flags.json"
            )
        self.red_flags_data = []
        if os.path.exists(red_flags_path):
            with open(red_flags_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.red_flags_data = data.get("red_flags", [])

    def check_red_flag(self, transcript: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Runs a deterministic check against all red-flag patterns.
        FR-12: This filter overrides the LLM. It can never be removed by an LLM.
        """
        if not transcript or not transcript.strip():
            return False, None

        cleaned = re.sub(r"[^\w\s]", " ", transcript.lower())
        tokens = cleaned.split()
        normalized_text = " ".join(tokens)

        for category in self.red_flags_data:
            cat_name = category.get("category")
            patterns = category.get("patterns", [])
            for pattern in patterns:
                pat_norm = " ".join(re.sub(r"[^\w\s]", " ", pattern.lower()).split())
                if pat_norm in normalized_text:
                    return True, {
                        "category": cat_name,
                        "matched_pattern": pattern,
                        "severity": category.get("severity", "CRITICAL"),
                        "description": category.get("description", "")
                    }

        return False, None

    def build_emergency_response(
        self,
        transcript: str,
        matched_details: Dict[str, Any],
        has_linked_caregivers: bool
    ) -> Dict[str, Any]:
        """UX-27 / FR-13: Constructs the emergency response view.
        Gives no medical advice. Returns calm emergency guidance and alert status.
        """
        if has_linked_caregivers:
            family_status = "Your family has been alerted immediately."
        else:
            family_status = "No family member is linked yet. Please call emergency services directly."

        spoken_instruction = (
            f"Please call the emergency number 911 immediately. {family_status}"
        )
        answer = (
            f"EMERGENCY DETECTED: {matched_details.get('description', 'Critical symptom')}.\n"
            f"Please press 'Call emergency number' now. {family_status}"
        )

        return {
            "transcript": transcript,
            "answer": answer,
            "source_line": None,
            "cited_line_ids": [],
            "confidence": 1.0,
            "confidence_badge": "Certain",
            "audio_url": "/static/audio/emergency_alert.wav",
            "ui_state": "emergency",
            "is_emergency": True,
            "emergency_action_taken": f"Urgent 911 banner displayed and high-priority alert fanned out. {family_status}"
        }


safety_service = SafetyService()
