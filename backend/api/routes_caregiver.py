"""Caregiver Dashboard and Clinician Review API endpoints.
Enforces SRS Section 7.2, FR-18, FR-23, FR-26, UX-35 through UX-38 (English-only edition).
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from backend.models.schemas import (
    DashboardResponse,
    AlertHandleRequest,
    ReviewNoteRequest
)
from backend.api.auth import get_current_caregiver
from backend.services.dashboard_service import dashboard_service
from backend.services.alert_service import alert_service

router = APIRouter(prefix="/api", tags=["Caregiver Dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
async def get_caregiver_dashboard(
    caregiver: Dict[str, Any] = Depends(get_current_caregiver)
):
    """FR-23 / UX-35: Today's Status summary, alerts, review queue, adherence, and appointments
    scoped strictly to the linked patient only.
    """
    patient_id = caregiver["patient_id"]
    data = await dashboard_service.get_patient_dashboard(patient_id)
    return DashboardResponse(**data)


@router.post("/alerts/{alert_id}/handled")
async def mark_alert_handled(
    alert_id: int,
    caregiver: Dict[str, Any] = Depends(get_current_caregiver)
):
    """UX-36: Mark a red-flag or emergency alert as handled."""
    patient_id = caregiver["patient_id"]
    success = await alert_service.mark_handled(alert_id, patient_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found or already handled."
        )
    return {"status": "success", "message": "Alert marked as handled."}


@router.post("/review/{review_id}/note")
async def add_clinician_note(
    review_id: int,
    payload: ReviewNoteRequest,
    caregiver: Dict[str, Any] = Depends(get_current_caregiver)
):
    """UX-37: Review queue item: add clinician answer or note."""
    patient_id = caregiver["patient_id"]
    success = await dashboard_service.add_review_note(
        review_id=review_id,
        note=payload.clinician_note,
        patient_id=patient_id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review item not found."
        )
    return {"status": "success", "message": "Clinician note recorded."}


from fastapi.responses import StreamingResponse
from fastapi import Query
from backend.services.pairing_service import pairing_service
from backend.services.event_bus import event_bus
import asyncio
import json


@router.get("/caregiver/events")
async def stream_caregiver_events(
    token: Optional[str] = Query(None),
    authorization: Optional[str] = None
):
    """Real-time SSE event stream for caregiver PWA.
    Fires the emergency buzzer immediately when patient reports chest pain or emergency.
    """
    raw_token = token
    if not raw_token and authorization and authorization.startswith("Bearer "):
        raw_token = authorization[7:].strip()

    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Caregiver token required")

    caregiver = await pairing_service.verify_caregiver_token(raw_token)
    if not caregiver:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid caregiver session token")

    patient_id = caregiver["patient_id"]
    queue = event_bus.subscribe_caregiver(patient_id)

    async def event_generator():
        try:
            # Initial connection handshake event
            yield f"event: connected\ndata: {json.dumps({'status': 'listening', 'patient_id': patient_id})}\n\n"
            while True:
                try:
                    # Wait for message with 15s timeout for heartbeat ping
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    evt_type = msg.get("event", "message")
                    data_str = json.dumps(msg.get("data", {}))
                    yield f"event: {evt_type}\ndata: {data_str}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat ping
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe_caregiver(patient_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

