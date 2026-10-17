"""Provider Conformance Test Suite (PR-14).
Runs the 40-utterance test set and evaluates:
- Red-flag recall (target: 100%)
- Valid citations on grounded answers (target: 100%)
- Intent accuracy (target: >= 85%)
- Correct handoff on out-of-scope questions (target: >= 90%)
"""
import os
import json
import pytest
from backend.config import settings
from backend.database import init_db_sync
from backend.services.turn_orchestrator import turn_orchestrator

DATASET_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend", "data", "conformance_dataset.json")


@pytest.fixture(autouse=True)
def setup_db():
    init_db_sync()


@pytest.mark.asyncio
async def test_40_utterance_conformance_benchmark():
    assert os.path.exists(DATASET_PATH), "Conformance dataset must exist"
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    assert len(dataset) == 40, f"Expected 40 utterances, found {len(dataset)}"

    total_utterances = len(dataset)
    red_flag_cases = 0
    red_flag_detected = 0
    intent_correct = 0
    grounded_cases = 0
    grounded_valid_citations = 0
    out_of_scope_cases = 0
    out_of_scope_handoffs = 0

    patient_id = "default-patient"
    orig_provider = settings.AI_PROVIDER
    settings.AI_PROVIDER = "mock"
    try:
        for item in dataset:
            utterance = item["utterance"]
            expected_intent = item["expected_intent"]
            expected_rf = item["expected_red_flag"]
            expected_cites = item.get("expected_citations", [])
            is_oos = item.get("is_out_of_scope", False)

            result = await turn_orchestrator.process_turn(
                patient_id=patient_id,
                text=utterance,
                script="en"
            )

            actual_intent = result["ui_state"]

            if expected_rf:
                red_flag_cases += 1
                if result.get("is_emergency") is True:
                    red_flag_detected += 1

            if is_oos:
                out_of_scope_cases += 1
                if result["ui_state"] == "handoff":
                    out_of_scope_handoffs += 1

            # Check intent classification
            if expected_intent == "emergency" and result["ui_state"] == "emergency":
                intent_correct += 1
            elif expected_intent in ["reminder", "appointment"] and result["ui_state"] == "waiting_confirmation":
                intent_correct += 1
            elif expected_intent == "qa" and result["ui_state"] == "speaking":
                intent_correct += 1
            elif expected_intent == "handoff" and result["ui_state"] == "handoff":
                intent_correct += 1

            # Check grounding citation validity
            if result["ui_state"] == "speaking":
                grounded_cases += 1
                cited = result.get("cited_line_ids", [])
                if cited and all(cid in ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8"] for cid in cited):
                    grounded_valid_citations += 1

        rf_recall = (red_flag_detected / red_flag_cases) * 100.0 if red_flag_cases else 100.0
        intent_acc = (intent_correct / total_utterances) * 100.0
        citation_validity = (grounded_valid_citations / grounded_cases) * 100.0 if grounded_cases else 100.0
        oos_handoff_rate = (out_of_scope_handoffs / out_of_scope_cases) * 100.0 if out_of_scope_cases else 100.0

        print("\n--- PR-14 Conformance Benchmark Results ---")
        print(f"Total Utterances: {total_utterances}")
        print(f"Red-Flag Recall: {rf_recall:.1f}% (Target: 100%)")
        print(f"Intent Accuracy: {intent_acc:.1f}% (Target: >= 85%)")
        print(f"Valid Citations on Grounded Answers: {citation_validity:.1f}% (Target: 100%)")
        print(f"Out-of-Scope Handoff Rate: {oos_handoff_rate:.1f}% (Target: >= 90%)")

        # Rigorous acceptance criteria
        assert rf_recall == 100.0, f"Red-flag recall {rf_recall}% did not meet 100% target"
        assert citation_validity == 100.0, f"Citation validity {citation_validity}% did not meet 100% target"
        assert intent_acc >= 85.0, f"Intent accuracy {intent_acc}% did not meet 85% target"
        assert oos_handoff_rate >= 90.0, f"Handoff rate {oos_handoff_rate}% did not meet 90% target"
    finally:
        settings.AI_PROVIDER = orig_provider
