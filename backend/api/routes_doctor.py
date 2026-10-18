"""Doctor Directory & Email Consultation API Endpoints.
it allows patients/caregivers to manage doctor information and personal Gmail,
draft concise clinical update emails for health issues, and explicitly approve
sending them.
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Header, HTTPException, status, Depends
from backend.models.schemas import (
    PatientProfile, PatientProfileUpdateRequest,
    DraftDoctorEmailRequest, DoctorEmailItem, ApproveDoctorEmailResponse
)
from backend.services.pairing_service import pairing_service
from backend.services.doctor_email_service import doctor_email_service
from backend.database import get_db_connection

router = APIRouter(prefix="/api", tags=["Doctor & Email Consultation"])


async def resolve_user_context(
    authorization: Optional[str] = Header(None),
    x_patient_token: Optional[str] = Header(None),
    x_caregiver_token: Optional[str] = Header(None)
) -> Dict[str, Any]:
    raw_token = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization[7:].strip()
    elif x_patient_token:
        raw_token = x_patient_token.strip()
    elif x_caregiver_token:
        raw_token = x_caregiver_token.strip()

    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication token required")

    patient = await pairing_service.verify_patient_token(raw_token)
    if patient:
        return {"role": "patient", "patient_id": patient["id"], "display_name": patient["display_name"]}

    caregiver = await pairing_service.verify_caregiver_token(raw_token)
    if caregiver:
        return {"role": "caregiver", "patient_id": caregiver["patient_id"], "display_name": caregiver["caregiver_name"]}

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


@router.get("/patient/profile", response_model=PatientProfile)
async def get_patient_profile(user: Dict[str, Any] = Depends(resolve_user_context)):
    """Fetch patient profile, personal Gmail, and linked doctor information."""
    conn = await get_db_connection()
    try:
        cursor = await conn.execute(
            "SELECT id, display_name, email, phone, age, emergency_contact_name, doctor_name, doctor_email, doctor_specialty, doctor_phone, created_at FROM patients WHERE id = ?",
            (user["patient_id"],)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient profile not found")

        return PatientProfile(
            patient_id=row["id"],
            display_name=row["display_name"],
            email=row["email"],
            phone=row["phone"],
            age=row["age"],
            emergency_contact_name=row["emergency_contact_name"],
            doctor_name=row["doctor_name"] or "Dr. Sarah Mitchell",
            doctor_email=row["doctor_email"] or "dr.sarah@gmail.com",
            doctor_specialty=row["doctor_specialty"] or "Cardiologist / General Physician",
            doctor_phone=row["doctor_phone"] or "+1-555-0199",
            created_at=row["created_at"] or ""
        )
    finally:
        await conn.close()


@router.put("/patient/profile", response_model=PatientProfile)
async def update_patient_profile(
    payload: PatientProfileUpdateRequest,
    user: Dict[str, Any] = Depends(resolve_user_context)
):
    """Update personal Gmail, doctor name, doctor Gmail, specialty, or phone."""
    conn = await get_db_connection()
    try:
        # Build dynamic update
        updates = []
        params = []
        if payload.display_name is not None:
            updates.append("display_name = ?")
            params.append(payload.display_name.strip())
        if payload.email is not None:
            updates.append("email = ?")
            params.append(payload.email.strip())
        if payload.phone is not None:
            updates.append("phone = ?")
            params.append(payload.phone.strip())
        if payload.age is not None:
            updates.append("age = ?")
            params.append(payload.age)
        if payload.emergency_contact_name is not None:
            updates.append("emergency_contact_name = ?")
            params.append(payload.emergency_contact_name.strip())
        if payload.doctor_name is not None:
            updates.append("doctor_name = ?")
            params.append(payload.doctor_name.strip())
        if payload.doctor_email is not None:
            updates.append("doctor_email = ?")
            params.append(payload.doctor_email.strip())
        if payload.doctor_specialty is not None:
            updates.append("doctor_specialty = ?")
            params.append(payload.doctor_specialty.strip())
        if payload.doctor_phone is not None:
            updates.append("doctor_phone = ?")
            params.append(payload.doctor_phone.strip())

        if updates:
            params.append(user["patient_id"])
            sql = f"UPDATE patients SET {', '.join(updates)} WHERE id = ?"
            await conn.execute(sql, params)
            await conn.commit()

        cursor = await conn.execute(
            "SELECT id, display_name, email, phone, age, emergency_contact_name, doctor_name, doctor_email, doctor_specialty, doctor_phone, created_at FROM patients WHERE id = ?",
            (user["patient_id"],)
        )
        row = await cursor.fetchone()
        return PatientProfile(
            patient_id=row["id"],
            display_name=row["display_name"],
            email=row["email"],
            phone=row["phone"],
            age=row["age"],
            emergency_contact_name=row["emergency_contact_name"],
            doctor_name=row["doctor_name"],
            doctor_email=row["doctor_email"],
            doctor_specialty=row["doctor_specialty"],
            doctor_phone=row["doctor_phone"],
            created_at=row["created_at"] or ""
        )
    finally:
        await conn.close()


@router.post("/doctor/draft-email", response_model=DoctorEmailItem)
async def draft_doctor_email(
    payload: DraftDoctorEmailRequest,
    user: Dict[str, Any] = Depends(resolve_user_context)
):
    """Drafts an email for the doctor regarding a health issue.
    STRICT: Saved as 'draft' only. The agent NEVER sends automatically.
    """
    draft = await doctor_email_service.draft_doctor_email(
        patient_id=user["patient_id"],
        health_issue=payload.health_issue,
        override_doctor_name=payload.doctor_name,
        override_doctor_email=payload.doctor_email
    )
    return DoctorEmailItem(**draft)


@router.post("/doctor/emails/{email_id}/approve", response_model=ApproveDoctorEmailResponse)
async def approve_and_send_doctor_email(
    email_id: int,
    user: Dict[str, Any] = Depends(resolve_user_context)
):
    """Explicitly authorizes the agent to send the drafted email to the doctor."""
    try:
        result = await doctor_email_service.approve_and_send_email(
            email_id=email_id,
            patient_id=user["patient_id"]
        )
        return ApproveDoctorEmailResponse(
            status="sent",
            message=result["message"],
            email_item=DoctorEmailItem(**result["email_item"])
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/doctor/emails/{email_id}/decline")
async def decline_doctor_email(
    email_id: int,
    user: Dict[str, Any] = Depends(resolve_user_context)
):
    """Declines sending the email draft."""
    success = await doctor_email_service.decline_email(email_id=email_id, patient_id=user["patient_id"])
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email draft not found")
    return {"status": "declined", "message": "Email draft has been declined."}


@router.get("/doctor/emails", response_model=List[DoctorEmailItem])
async def list_doctor_emails(user: Dict[str, Any] = Depends(resolve_user_context)):
    """List all email drafts and sent consultations."""
    items = await doctor_email_service.list_patient_emails(user["patient_id"])
    return [DoctorEmailItem(**i) for i in items]
