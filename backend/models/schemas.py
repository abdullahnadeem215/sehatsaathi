"""Pydantic schemas for Sehat Saathi API requests and responses (English-only Edition).
"""
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime


# --- Auth & Registration ---
class PatientRegisterRequest(BaseModel):
    display_name: str = Field(default="Robert Jenkins", description="Patient name")
    email: Optional[str] = Field(default=None, description="Patient's personal Gmail / email")
    phone: Optional[str] = Field(default=None, description="Patient's contact or emergency phone")
    age: Optional[int] = Field(default=None, description="Patient's age")
    emergency_contact_name: Optional[str] = Field(default=None, description="Family or emergency contact person")
    doctor_name: Optional[str] = Field(default=None, description="Primary doctor's name")
    doctor_email: Optional[str] = Field(default=None, description="Primary doctor's Gmail / email")
    doctor_specialty: Optional[str] = Field(default=None, description="Doctor specialty / clinic")
    doctor_phone: Optional[str] = Field(default=None, description="Doctor clinic phone")
    preferred_script: Literal["en"] = Field(default="en", description="English language setting")


class PatientRegisterResponse(BaseModel):
    patient_id: str
    display_name: str
    email: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_email: Optional[str] = None
    device_token: str
    message: str


# --- Turn & Dialogue Pipeline ---
class TurnRequest(BaseModel):
    text: Optional[str] = Field(default=None, description="Typed question or fallback text")
    script: Literal["en"] = Field(default="en", description="Language setting")
    audio_base64: Optional[str] = Field(default=None, description="Base64 encoded audio input if spoken")


class TurnResponse(BaseModel):
    transcript: str
    answer: str
    source_line: Optional[str] = None
    cited_line_ids: List[str] = []
    confidence: float
    confidence_badge: Literal["Certain", "Possibly", "Unknown"]
    audio_url: Optional[str] = None
    ui_state: Literal["listening", "thinking", "speaking", "waiting_confirmation", "emergency", "handoff"]
    echo_back: Optional[str] = None
    pending_action_id: Optional[str] = None
    is_emergency: bool = False
    emergency_action_taken: Optional[str] = None
    tool_called: Optional[str] = Field(default=None, description="LLM-selected tool: alert_caregiver | draft_doctor_email | create_reminder | book_appointment | answer_discharge_question")
    email_draft: Optional[Dict[str, Any]] = Field(default=None, description="Drafted doctor email awaiting patient approval")
    alert_info: Optional[Dict[str, Any]] = Field(default=None, description="Details of caregiver alert dispatched")



# --- Confirm-Before-Act ---
class ConfirmRequest(BaseModel):
    action_id: str
    confirmed: bool
    spoken_reply: Optional[str] = None  # e.g., "yes", "that is correct", "no"


class ConfirmResponse(BaseModel):
    status: Literal["confirmed", "rejected", "expired"]
    message: str
    details: Optional[Dict[str, Any]] = None


# --- Reminders ---
class ReminderItem(BaseModel):
    id: int
    patient_id: str
    medicine_name: str
    dose_text: str
    timing_text: str
    status: str
    created_at: str


class ReminderActionRequest(BaseModel):
    action: Literal["taken", "snoozed", "missed"]
    scheduled_time: Optional[str] = None


class MedicationIntakeRequest(BaseModel):
    reminder_id: Optional[int] = None
    medicine_name: Optional[str] = None
    time_offset_minutes: int = Field(default=0, description="Time offset in minutes if taken in the past, e.g. 60 for 1 hour ago")
    intake_note: Optional[str] = None


# --- Prescriptions (Caregiver & Patient) ---
class PrescriptionCreateRequest(BaseModel):
    medicine_name: str = Field(description="Name of the medicine, e.g. Aspirin")
    dose_text: str = Field(description="Dose, e.g. 75mg or 1 tablet")
    timing_text: str = Field(description="Timing, e.g. once daily with dinner")
    instructions: Optional[str] = Field(default=None, description="Special instructions, e.g. Take with water")


class PrescriptionItem(BaseModel):
    id: int
    patient_id: str
    added_by: str  # 'caregiver' or 'patient'
    author_name: str
    medicine_name: str
    dose_text: str
    timing_text: str
    instructions: Optional[str] = None
    status: str
    created_at: str


# --- Appointments & Slots ---
class SlotItem(BaseModel):
    slot_id: str
    slot_start: str
    display_text: str
    available: bool


class SlotListResponse(BaseModel):
    slots: List[SlotItem]


class AppointmentItem(BaseModel):
    id: int
    patient_id: str
    slot_start: str
    status: str
    created_at: str


# --- Pairing & Access Control (FR-18 to FR-25) ---
class PairCreateResponse(BaseModel):
    key: str
    formatted_key: str  # e.g., "A3F9-7C21"
    expires_in_seconds: int
    expires_at: str


class PairRedeemRequest(BaseModel):
    key: str = Field(description="8-hex character key, accepts dashes/spaces and case insensitive")
    caregiver_name: str = Field(description="Caregiver display name")


class PairRedeemResponse(BaseModel):
    pending_id: int
    message: str


class PairPendingItem(BaseModel):
    pending_id: int
    caregiver_name: str
    created_at: str


class PairDecideRequest(BaseModel):
    pending_id: int
    approve: bool


class PairDecideResponse(BaseModel):
    status: Literal["approved", "declined"]
    message: str


class PairStatusResponse(BaseModel):
    status: Literal["pending", "approved", "declined", "expired"]
    session_token: Optional[str] = None
    caregiver_name: Optional[str] = None
    message: str


class CaregiverLinkItem(BaseModel):
    id: int
    caregiver_name: str
    status: str
    created_at: str
    revoked_at: Optional[str] = None


# --- Dashboard (Caregiver Scoped, UX-35) ---
class DashboardSummary(BaseModel):
    patient_display_name: str
    open_alerts_count: int
    review_items_count: int
    reminders_taken_today: int
    reminders_missed_today: int
    reminders_pending_today: int
    next_appointment: Optional[str] = None


class AlertItem(BaseModel):
    id: int
    type: str
    priority: str
    transcript_excerpt: Optional[str] = None
    action_taken: Optional[str] = None
    created_at: str
    handled_at: Optional[str] = None


class ReviewQueueItem(BaseModel):
    id: int
    question: str
    attempted_answer: Optional[str] = None
    cited_line_ids: Optional[str] = None
    reason: Optional[str] = None
    clinician_note: Optional[str] = None
    status: str
    created_at: str


class DashboardResponse(BaseModel):
    summary: DashboardSummary
    alerts: List[AlertItem]
    review_queue: List[ReviewQueueItem]
    reminders: List[ReminderItem]
    appointments: List[AppointmentItem]


class AlertHandleRequest(BaseModel):
    note: Optional[str] = None


class ReviewNoteRequest(BaseModel):
    clinician_note: str


# --- Operator Health ---
class CapabilityHealth(BaseModel):
    provider: str
    model: str
    last_call: Optional[str] = None
    recent_latency_ms: Optional[float] = None


class OperatorHealthResponse(BaseModel):
    status: str
    global_ai_provider: str
    auto_fallback: bool
    fallback_provider: str
    capabilities: Dict[str, CapabilityHealth]


# --- Patient Profile & Doctor Directory ---
class PatientProfile(BaseModel):
    patient_id: str
    display_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    age: Optional[int] = None
    emergency_contact_name: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_email: Optional[str] = None
    doctor_specialty: Optional[str] = None
    doctor_phone: Optional[str] = None
    created_at: str


class PatientProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    age: Optional[int] = None
    emergency_contact_name: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_email: Optional[str] = None
    doctor_specialty: Optional[str] = None
    doctor_phone: Optional[str] = None


class DoctorItem(BaseModel):
    id: Optional[int] = None
    name: str
    email: str
    specialty: Optional[str] = None
    phone: Optional[str] = None


# --- Prescription OCR Extraction ---
class ExtractedMedicineItem(BaseModel):
    medicine_name: str
    dose_text: str
    timing_text: str
    instructions: Optional[str] = None
    missing_fields: List[str] = []
    confidence: float = 0.9


class PrescriptionOCRResponse(BaseModel):
    raw_text: str
    extracted_medicines: List[ExtractedMedicineItem]
    missing_summary: Optional[str] = None
    has_missing_info: bool = False


# --- Doctor Email Consultation & Approval Flow ---
class DraftDoctorEmailRequest(BaseModel):
    health_issue: str = Field(description="Description of patient's current health issue or symptoms")
    doctor_name: Optional[str] = None
    doctor_email: Optional[str] = None


class DoctorEmailItem(BaseModel):
    id: int
    patient_id: str
    doctor_name: str
    doctor_email: str
    patient_email: Optional[str] = None
    subject: str
    body: str
    health_issue: str
    prescriptions_summary: Optional[str] = None
    status: Literal["draft", "approved", "sent", "declined"]
    created_at: str
    sent_at: Optional[str] = None


class ApproveDoctorEmailResponse(BaseModel):
    status: Literal["sent", "failed"]
    message: str
    email_item: DoctorEmailItem
