"""Tests for Real-time Emergency Buzzer Broadcast and Prescription Management.
Verifies that:
1. Patient saying "I have the pain in my heart so hard" immediately triggers an emergency and broadcasts to caregiver SSE.
2. Caregivers (and patients) can add prescriptions.
3. Added prescription creates active reminders and dynamically adds lines to summary_lines for immediate grounding.
"""
import pytest
import asyncio
from backend.database import init_db_sync
from backend.services.turn_orchestrator import turn_orchestrator
from backend.services.pairing_service import pairing_service
from backend.services.prescription_service import prescription_service
from backend.services.event_bus import event_bus
from backend.services.safety_service import safety_service


@pytest.fixture(autouse=True)
def setup_db():
    init_db_sync()


@pytest.mark.asyncio
async def test_heart_pain_emergency_buzzer_broadcast():
    # 1. Register patient
    patient_id, p_token = await pairing_service.register_patient_device("Grandma Rose")

    # 2. Pair a caregiver
    raw_key, _, _, _ = await pairing_service.generate_pairing_key(patient_id)
    _, pending_id, _ = await pairing_service.redeem_pairing_key(raw_key, "Caring Granddaughter", "127.0.0.1")
    await pairing_service.decide_link_request(patient_id, pending_id, approve=True)
    _, cg_token, _, _ = await pairing_service.check_pairing_status(pending_id)

    # 3. Subscribe caregiver to event_bus queue (simulating SSE connection)
    cg_queue = event_bus.subscribe_caregiver(patient_id)

    try:
        # 4. Patient speaks suddenly: "I have the pain in my heart so hard"
        turn_result = await turn_orchestrator.process_turn(
            patient_id=patient_id,
            text="I have the pain in my heart so hard",
            script="en"
        )

        # Assert emergency detected on patient device
        assert turn_result["is_emergency"] is True
        assert turn_result["ui_state"] == "emergency"
        assert "emergency" in turn_result["answer"].lower()

        # Assert caregiver received emergency_buzzer event immediately over event_bus
        event = await asyncio.wait_for(cg_queue.get(), timeout=2.0)
        assert event["event"] == "emergency_buzzer"
        assert event["patient_id"] == patient_id
        assert event["data"]["sound_buzzer"] is True
        assert event["data"]["patient_name"] == "Grandma Rose"
        assert "heart" in event["data"]["transcript_excerpt"].lower()
    finally:
        event_bus.unsubscribe_caregiver(patient_id, cg_queue)


@pytest.mark.asyncio
async def test_prescription_addition_and_grounding_sync():
    # 1. Register patient
    patient_id, _ = await pairing_service.register_patient_device("Arthur Morgan")

    # 2. Caregiver adds prescription: "Aspirin 75mg once daily with dinner"
    rx = await prescription_service.add_prescription(
        patient_id=patient_id,
        added_by="caregiver",
        author_name="Nurse Mary",
        medicine_name="Aspirin",
        dose_text="75mg",
        timing_text="once daily with dinner",
        instructions="Take with full glass of water"
    )

    assert rx["id"] is not None
    assert rx["medicine_name"] == "Aspirin"
    assert rx["dose_text"] == "75mg"
    assert rx["grounded_line_id"] is not None

    # 3. Verify active prescription retrieved
    active_rxs = await prescription_service.get_active_prescriptions(patient_id)
    assert len(active_rxs) >= 1
    assert any(r["medicine_name"] == "Aspirin" for r in active_rxs)

    # 4. Verify summary lines have been dynamically updated for AI grounding
    summary_lines = await turn_orchestrator._get_patient_summary_lines(patient_id)
    new_lines = [l for l in summary_lines if "Aspirin" in l["text"]]
    assert len(new_lines) > 0
    assert "75mg" in new_lines[0]["text"]
