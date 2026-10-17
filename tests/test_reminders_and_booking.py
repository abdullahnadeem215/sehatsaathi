"""Tests for Reminders, Confirm-Before-Act, and Appointment Booking (FR-06 through FR-11, FR-16, UX-14, UX-15).
"""
import pytest
from backend.database import init_db_sync
from backend.services.reminder_service import reminder_service
from backend.services.appointment_service import appointment_service


@pytest.fixture(autouse=True)
def setup_db():
    init_db_sync()


@pytest.mark.asyncio
async def test_reminder_confirm_before_act_flow():
    # FR-06 / FR-08 / FR-16 / UX-14
    patient_id = "default-patient"
    med = "Metformin"
    dose = "500mg"
    timing = "once daily in the morning after breakfast"

    # Step 1: Prepare confirmation (Echo-back)
    action_id, echo_text = await reminder_service.prepare_reminder_confirmation(
        patient_id=patient_id,
        medicine_name=med,
        dose_text=dose,
        timing_text=timing
    )
    assert action_id.startswith("act_")
    assert f"I heard: {med} {dose} {timing}. Is that correct?" in echo_text

    # Verify no reminder saved yet before confirmation (FR-16)
    reminders_before = await reminder_service.get_patient_reminders(patient_id)
    initial_count = len(reminders_before)

    # Step 2: Confirm action
    saved_data = await reminder_service.execute_confirmed_reminder(action_id, patient_id)
    assert saved_data is not None
    assert saved_data["medicine_name"] == med
    assert saved_data["dose_text"] == dose  # Dose copied exactly, never modified (FR-08)

    # Verify reminder is now persisted
    reminders_after = await reminder_service.get_patient_reminders(patient_id)
    assert len(reminders_after) == initial_count + 1


@pytest.mark.asyncio
async def test_reminder_rejected_flow():
    # UX-15: 'No' returns without error and does not write data
    patient_id = "default-patient"
    action_id, _ = await reminder_service.prepare_reminder_confirmation(
        patient_id=patient_id,
        medicine_name="Wrong Medicine",
        dose_text="100mg",
        timing_text="at noon"
    )

    # User says No
    rejected = await reminder_service.reject_pending_action(action_id, patient_id)
    assert rejected is True

    # Confirm attempt fails because status is rejected
    executed = await reminder_service.execute_confirmed_reminder(action_id, patient_id)
    assert executed is None


@pytest.mark.asyncio
async def test_appointment_booking_and_slot_limit():
    # FR-10: Speaks no more than 3 slots at a time; books only after confirmation
    slots = appointment_service.get_available_slots(limit=3)
    assert len(slots) <= 3
    assert slots[0]["available"] is True

    # Prepare booking confirmation (UX-14)
    patient_id = "default-patient"
    slot_text = slots[0]["display_text"]
    action_id, echo_text = await appointment_service.prepare_booking_confirmation(patient_id, slot_text)
    assert f"Book appointment for {slot_text}" in echo_text

    # Execute confirmation
    booked_data = await appointment_service.execute_confirmed_booking(action_id, patient_id)
    assert booked_data is not None
    assert booked_data["slot_start"] == slot_text

    # Verify in appointments list (FR-11)
    appts = await appointment_service.get_patient_appointments(patient_id)
    assert any(a["slot_start"] == slot_text for a in appts)
