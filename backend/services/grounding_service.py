"""Grounding and citation verification service.
Enforces SRS FR-02, FR-03, FR-05, FR-14, FR-15, UX-16, UX-28 (English-only edition).
"""
from typing import List, Dict, Any, Tuple, Optional
from backend.config import settings

HONEST_HANDOFF_TEXT = (
    "This information is not in your discharge summary. "
    "I have made a note so your doctor or family can be informed."
)


class GroundingService:
    def __init__(self, confidence_threshold: float = settings.CONFIDENCE_THRESHOLD):
        self.confidence_threshold = confidence_threshold

    def verify_grounding(
        self,
        llm_answer: str,
        cited_line_ids: List[str],
        confidence: float,
        summary_lines: List[Dict[str, Any]]
    ) -> Tuple[bool, str, Optional[str], str]:
        """Validates that cited line IDs exist in the discharge summary.
        Returns: (is_grounded, final_answer, source_line_text, confidence_badge)
        """
        valid_line_map = {line["line_id"]: line["text"] for line in summary_lines}

        # Confidence badge calculation
        if confidence >= 0.85:
            badge = "Certain"
        elif confidence >= self.confidence_threshold:
            badge = "Possibly"
        else:
            badge = "Unknown"

        # Check: must cite at least one line ID and all cited IDs must exist
        if not cited_line_ids or len(cited_line_ids) == 0:
            return False, HONEST_HANDOFF_TEXT, None, "Unknown"

        for line_id in cited_line_ids:
            if line_id not in valid_line_map:
                # FR-03: If any ID is invalid, convert to honest handoff
                return False, HONEST_HANDOFF_TEXT, None, "Unknown"

        # Check: confidence threshold
        if confidence < self.confidence_threshold:
            # FR-14: Below threshold converted to honest handoff
            return False, HONEST_HANDOFF_TEXT, None, "Unknown"

        # Formulate source line text (UX-16)
        source_texts = [valid_line_map[lid] for lid in cited_line_ids]
        source_line = "Your discharge summary says: " + " ".join(source_texts)

        return True, llm_answer, source_line, badge

    def build_safety_failure_handoff(self, reason: str = "Provider failure") -> Dict[str, Any]:
        """FR-15: Provider failure/timeout/empty answer results in honest handoff."""
        return {
            "answer": HONEST_HANDOFF_TEXT,
            "source_line": None,
            "cited_line_ids": [],
            "confidence": 0.0,
            "confidence_badge": "Unknown",
            "ui_state": "handoff",
            "handoff_reason": f"System error or timeout: {reason}"
        }


grounding_service = GroundingService()
