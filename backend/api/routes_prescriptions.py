"""Prescription API Endpoints for Patient and Caregiver.
Enables simple addition and retrieval of active prescriptions.
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Header, HTTPException, status, Depends
from backend.models.schemas import PrescriptionCreateRequest, PrescriptionItem
from backend.services.prescription_service import prescription_service
from backend.services.pairing_service import pairing_service

router = APIRouter(prefix="/api/prescriptions", tags=["Prescriptions"])


async def resolve_user_context(
    authorization: Optional[str] = Header(None),
    x_patient_token: Optional[str] = Header(None),
    x_caregiver_token: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """Resolves whether the caller is an authenticated patient or caregiver."""
    raw_token = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization[7:].strip()
    elif x_patient_token:
        raw_token = x_patient_token.strip()
    elif x_caregiver_token:
        raw_token = x_caregiver_token.strip()

    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication token required")

    # Check patient token first
    patient = await pairing_service.verify_patient_token(raw_token)
    if patient:
        return {
            "role": "patient",
            "patient_id": patient["id"],
            "display_name": patient["display_name"]
        }

    # Check caregiver token
    caregiver = await pairing_service.verify_caregiver_token(raw_token)
    if caregiver:
        return {
            "role": "caregiver",
            "patient_id": caregiver["patient_id"],
            "display_name": caregiver["caregiver_name"]
        }

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


@router.post("", response_model=PrescriptionItem)
async def create_prescription(
    payload: PrescriptionCreateRequest,
    user: Dict[str, Any] = Depends(resolve_user_context)
):
    """Add a new prescription. Automatically creates a medicine reminder and
    dynamically adds the medication into summary lines for immediate AI grounding.
    """
    rx = await prescription_service.add_prescription(
        patient_id=user["patient_id"],
        added_by=user["role"],
        author_name=user["display_name"],
        medicine_name=payload.medicine_name,
        dose_text=payload.dose_text,
        timing_text=payload.timing_text,
        instructions=payload.instructions
    )
    return PrescriptionItem(**rx)


@router.get("", response_model=List[PrescriptionItem])
async def list_prescriptions(
    user: Dict[str, Any] = Depends(resolve_user_context)
):
    """List current active prescriptions for the patient."""
    items = await prescription_service.get_active_prescriptions(user["patient_id"])
    return [PrescriptionItem(**i) for i in items]


@router.delete("/{prescription_id}")
async def remove_prescription(
    prescription_id: int,
    user: Dict[str, Any] = Depends(resolve_user_context)
):
    """Deactivate a prescription."""
    success = await prescription_service.deactivate_prescription(user["patient_id"], prescription_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription not found")
    return {"status": "success", "message": "Prescription removed"}


from fastapi import UploadFile, File, Form, Body
from backend.models.schemas import PrescriptionOCRResponse
from backend.services.ocr_service import ocr_service
import base64


@router.post("/upload-image", response_model=PrescriptionOCRResponse)
async def upload_prescription_image(
    file: Optional[UploadFile] = File(None),
    image_base64: Optional[str] = Form(None),
    user: Dict[str, Any] = Depends(resolve_user_context)
):
    """Accepts prescription image upload via multipart or base64, runs OCR,
    and identifies missing clinical details such as timing of medication.
    """
    image_bytes = b""
    filename = "prescription.jpg"

    if file:
        image_bytes = await file.read()
        filename = file.filename or filename
    elif image_base64:
        clean_b64 = image_base64.strip()
        if "," in clean_b64:
            clean_b64 = clean_b64.split(",")[1]
        padded = clean_b64 + "=" * (-len(clean_b64) % 4)
        image_bytes = base64.b64decode(padded)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No image file or base64 provided")

    result = await ocr_service.extract_from_image_bytes(image_bytes, filename)
    return PrescriptionOCRResponse(**result)
