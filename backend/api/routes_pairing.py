"""Caregiver Pairing and Consent API endpoints.
Enforces SRS Section 7.2, FR-18 through FR-26, UX-39 through UX-44 (English-only edition).
"""
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from backend.models.schemas import (
    PairCreateResponse,
    PairRedeemRequest, PairRedeemResponse,
    PairPendingItem,
    PairDecideRequest, PairDecideResponse,
    PairStatusResponse,
    CaregiverLinkItem
)
from backend.api.auth import get_current_patient
from backend.services.pairing_service import pairing_service

router = APIRouter(prefix="/api/pair", tags=["Pairing & Consent"])


@router.post("/create", response_model=PairCreateResponse)
async def create_pairing_key(
    patient: Dict[str, Any] = Depends(get_current_patient)
):
    """FR-20 / UX-41: Generate an 8-hex character pairing key with 10-minute expiry."""
    raw_key, formatted_key, ttl_sec, expires_at = await pairing_service.generate_pairing_key(
        patient_id=patient["id"]
    )
    return PairCreateResponse(
        key=raw_key,
        formatted_key=formatted_key,
        expires_in_seconds=ttl_sec,
        expires_at=expires_at
    )


@router.post("/redeem", response_model=PairRedeemResponse)
async def redeem_pairing_key(
    payload: PairRedeemRequest,
    request: Request
):
    """FR-21 / FR-25 / UX-43: Submit key and caregiver name; initiates consent step. Rate limited."""
    client_ip = request.client.host if request.client else "127.0.0.1"

    success, pending_id, message = await pairing_service.redeem_pairing_key(
        raw_key=payload.key,
        caregiver_name=payload.caregiver_name,
        client_ip=client_ip
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )

    return PairRedeemResponse(
        pending_id=pending_id,  # type: ignore
        message=message
    )


@router.get("/pending", response_model=List[PairPendingItem])
async def list_pending_requests(
    patient: Dict[str, Any] = Depends(get_current_patient)
):
    """UX-42: Patient polls for pending link requests awaiting approval."""
    items = await pairing_service.get_pending_requests(patient["id"])
    return [PairPendingItem(**i) for i in items]


@router.post("/decide", response_model=PairDecideResponse)
async def decide_link_request(
    payload: PairDecideRequest,
    patient: Dict[str, Any] = Depends(get_current_patient)
):
    """FR-22 / UX-42: Patient approves or declines caregiver request."""
    success, message = await pairing_service.decide_link_request(
        patient_id=patient["id"],
        pending_id=payload.pending_id,
        approve=payload.approve
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    return PairDecideResponse(
        status="approved" if payload.approve else "declined",
        message=message
    )


@router.get("/status", response_model=PairStatusResponse)
async def check_link_status(pending_id: int):
    """Caregiver device polls for approval; receives session token once on approval."""
    status_str, token, name, msg = await pairing_service.check_pairing_status(pending_id)
    return PairStatusResponse(
        status=status_str,  # type: ignore
        session_token=token,
        caregiver_name=name,
        message=msg
    )


@router.get("/links", response_model=List[CaregiverLinkItem])
async def list_linked_caregivers(
    patient: Dict[str, Any] = Depends(get_current_patient)
):
    """FR-24 / UX-40: List linked caregivers."""
    links = await pairing_service.list_patient_links(patient["id"])
    return [CaregiverLinkItem(**l) for l in links]


@router.delete("/links/{link_id}")
async def revoke_caregiver(
    link_id: int,
    patient: Dict[str, Any] = Depends(get_current_patient)
):
    """FR-24 / UX-44: Revoke a caregiver. Takes effect immediately."""
    success = await pairing_service.revoke_caregiver_link(
        patient_id=patient["id"],
        link_id=link_id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Caregiver link not found or already revoked."
        )
    return {"status": "revoked", "message": "Caregiver link has been revoked."}
