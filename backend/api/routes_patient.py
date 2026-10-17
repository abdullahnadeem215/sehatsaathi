"""Patient API endpoints.
Enforces SRS Section 7.2, FR-01 through FR-16, UX-14 through UX-30 (English-only edition).
"""
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from backend.models.schemas import (
    PatientRegisterRequest, PatientRegisterResponse,
    TurnRequest, TurnResponse,
    ConfirmRequest, ConfirmResponse,
    ReminderItem, ReminderActionRequest, MedicationIntakeRequest,
    SlotItem, SlotListResponse
)
from backend.api.auth import get_current_patient
from backend.services.pairing_service import pairing_service
from backend.services.turn_orchestrator import turn_orchestrator
from backend.services.reminder_service import reminder_service
from backend.services.appointment_service import appointment_service
from backend.services.alert_service import alert_service
from backend.services.doctor_email_service import doctor_email_service
from backend.services.conversation_memory_service import conversation_memory_service

router = APIRouter(prefix="/api", tags=["Patient"])


@router.post("/patient/register", response_model=PatientRegisterResponse)
@router.post("/patient/signup", response_model=PatientRegisterResponse)
async def register_patient(payload: PatientRegisterRequest):
    """FR-19: Create an individual patient record with personal/doctor details and issue device token."""
    patient_id, device_token = await pairing_service.register_patient_device(
        display_name=payload.display_name,
        email=payload.email,
        phone=payload.phone,
        age=payload.age,
        emergency_contact_name=payload.emergency_contact_name,
        doctor_name=payload.doctor_name,
        doctor_email=payload.doctor_email,
        doctor_specialty=payload.doctor_specialty,
        doctor_phone=payload.doctor_phone,
        seed_reminders=False
    )
    return PatientRegisterResponse(
        patient_id=patient_id,
        display_name=payload.display_name,
        email=payload.email,
        doctor_name=payload.doctor_name,
        doctor_email=payload.doctor_email,
        device_token=device_token,
        message="Patient account registered successfully. Your health companion is ready!"
    )


@router.post("/turn", response_model=TurnResponse)
async def handle_turn(
    payload: TurnRequest,
    patient: Dict[str, Any] = Depends(get_current_patient)
):
    """Submit audio or text question; receive transcript, grounded answer, citations, and state."""
    result = await turn_orchestrator.process_turn(
        patient_id=patient["id"],
        text=payload.text,
        audio_base64=payload.audio_base64,
        script="en"
    )
    return TurnResponse(**result)


@router.post("/confirm", response_model=ConfirmResponse)
async def confirm_action(
    payload: ConfirmRequest,
    patient: Dict[str, Any] = Depends(get_current_patient)
):
    """FR-16 / UX-14 / UX-15: Confirm or reject a pending reminder, booking, or doctor email."""
    action_id = payload.action_id
    patient_id = patient["id"]

    # Handle Doctor Email confirmation / decline
    if action_id.startswith("email_"):
        try:
            email_id = int(action_id.split("_")[1])
            if not payload.confirmed:
                await doctor_email_service.decline_email(email_id, patient_id)
                return ConfirmResponse(
                    status="rejected",
                    message="Email draft discarded. No email was sent to your doctor.",
                    details=None
                )
            res = await doctor_email_service.approve_and_send_email(email_id, patient_id)
            return ConfirmResponse(
                status="confirmed",
                message=res["message"],
                details=res["email_item"]
            )
        except Exception as e:
            return ConfirmResponse(
                status="expired",
                message=f"Could not process doctor email action: {e}",
                details=None
            )

    if not payload.confirmed:
        # UX-15: 'No' never causes an error state
        await reminder_service.reject_pending_action(action_id, patient_id)
        return ConfirmResponse(
            status="rejected",
            message="All right, please say it again.",
            details=None
        )

    # Attempt to confirm as reminder
    rem_data = await reminder_service.execute_confirmed_reminder(action_id, patient_id)
    if rem_data:
        return ConfirmResponse(
            status="confirmed",
            message=f"Reminder confirmed and saved for {rem_data['medicine_name']} {rem_data['dose_text']}.",
            details=rem_data
        )

    # Attempt to confirm as appointment
    appt_data = await appointment_service.execute_confirmed_booking(action_id, patient_id)
    if appt_data:
        return ConfirmResponse(
            status="confirmed",
            message=f"Appointment booked successfully for {appt_data['slot_start']}.",
            details=appt_data
        )

    return ConfirmResponse(
        status="expired",
        message="Pending action was not found or has expired. Please try again.",
        details=None
    )


@router.get("/reminders", response_model=List[ReminderItem])
async def list_patient_reminders(
    patient: Dict[str, Any] = Depends(get_current_patient)
):
    """List the patient's active reminders."""
    reminders = await reminder_service.get_patient_reminders(patient["id"])
    return [ReminderItem(**r) for r in reminders]


@router.get("/reminders/due")
async def get_due_reminder(
    patient: Dict[str, Any] = Depends(get_current_patient)
):
    """Checks if there is a reminder scheduled and returns a gentle prompt to ask if the patient took it."""
    return await reminder_service.get_due_reminder_prompt(patient["id"])


@router.post("/reminders/intake")
async def record_medication_intake(
    payload: MedicationIntakeRequest,
    patient: Dict[str, Any] = Depends(get_current_patient)
):
    """Record medication intake with optional natural language offset (e.g., 60 mins ago)."""
    return await reminder_service.record_natural_intake(
        patient_id=patient["id"],
        medicine_name=payload.medicine_name,
        time_offset_minutes=payload.time_offset_minutes,
        intake_note=payload.intake_note
    )


@router.post("/reminders/{reminder_id}/take")
async def take_reminder_with_offset(
    reminder_id: int,
    payload: MedicationIntakeRequest,
    patient: Dict[str, Any] = Depends(get_current_patient)
):
    """Quick intake confirmation for a specific reminder with optional past time offset."""
    reminders = await reminder_service.get_patient_reminders(patient["id"])
    med_name = payload.medicine_name
    for r in reminders:
        if r["id"] == reminder_id:
            med_name = r["medicine_name"]
            break

    return await reminder_service.record_natural_intake(
        patient_id=patient["id"],
        medicine_name=med_name,
        time_offset_minutes=payload.time_offset_minutes,
        intake_note=payload.intake_note
    )


@router.get("/patient/memory")
async def get_patient_memories(
    limit: int = 10,
    patient: Dict[str, Any] = Depends(get_current_patient)
):
    """Retrieve recent conversation memories for transparency and recall verification."""
    memories = await conversation_memory_service.get_recent_memories(patient["id"], limit=limit)
    return {"memories": memories}


@router.post("/reminders/{reminder_id}/action")
async def record_reminder_action(
    reminder_id: int,
    payload: ReminderActionRequest,
    patient: Dict[str, Any] = Depends(get_current_patient)
):
    """FR-09 / UX-30: Record medicine taken, snoozed, or missed for caregiver adherence view."""
    await reminder_service.record_adherence_action(
        reminder_id=reminder_id,
        patient_id=patient["id"],
        action=payload.action,
        scheduled_time=payload.scheduled_time
    )
    return {"status": "success", "message": f"Dose marked as {payload.action}."}


@router.get("/slots", response_model=SlotListResponse)
async def list_calendar_slots(
    patient: Dict[str, Any] = Depends(get_current_patient)
):
    """FR-10: List mock calendar slots (maximum 3 at a time)."""
    slots = appointment_service.get_available_slots(limit=3)
    return SlotListResponse(slots=[SlotItem(**s) for s in slots])


@router.post("/emergency/notify")
async def notify_family_emergency(
    patient: Dict[str, Any] = Depends(get_current_patient)
):
    """UX-17: One-tap 'Notify family' action which alerts all linked caregivers."""
    alert_id = await alert_service.create_and_fanout_alert(
        patient_id=patient["id"],
        alert_type="EMERGENCY_NOTIFY",
        priority="HIGH",
        transcript_excerpt="Patient pressed Help / Emergency button",
        action_taken="Emergency broadcast sent to all linked caregivers."
    )
    return {
        "status": "alerted",
        "alert_id": alert_id,
        "message": "Your linked family members have been alerted."
    }
