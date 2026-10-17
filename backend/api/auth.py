"""Authentication guards for Patient, Caregiver, and Operator endpoints.
Enforces SRS FR-18, FR-19, FR-23, PR-12, UX-44.
"""
from typing import Optional, Dict, Any
from fastapi import Header, HTTPException, status, Depends
from backend.config import settings
from backend.services.pairing_service import pairing_service
from backend.database import get_db_connection, hash_token


async def get_current_patient(
    authorization: Optional[str] = Header(None),
    x_patient_token: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """FR-19: Validates patient device token."""
    raw_token = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization[7:].strip()
    elif x_patient_token:
        raw_token = x_patient_token.strip()

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Patient device authentication required"
        )

    patient = await pairing_service.verify_patient_token(raw_token)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unregistered patient device token"
        )
    return patient


async def get_current_caregiver(
    authorization: Optional[str] = Header(None),
    x_caregiver_token: Optional[str] = Header(None),
    x_dashboard_code: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """FR-23 / UX-44: Validates caregiver session token and resolves linked patient_id.
    Never accepts client-supplied patient ID!
    """
    raw_token = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization[7:].strip()
    elif x_caregiver_token:
        raw_token = x_caregiver_token.strip()

    # Optional demo bypass if configured
    if settings.DASHBOARD_ACCESS_CODE and x_dashboard_code == settings.DASHBOARD_ACCESS_CODE:
        return {
            "patient_id": "default-patient",
            "caregiver_name": "Demo Operator",
            "status": "active"
        }

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Caregiver session token required"
        )

    # Check if active
    caregiver = await pairing_service.verify_caregiver_token(raw_token)
    if caregiver:
        return caregiver

    # Check if revoked (UX-44)
    token_hash = hash_token(raw_token)
    conn = await get_db_connection()
    try:
        cursor = await conn.execute(
            "SELECT status FROM caregiver_links WHERE token_hash = ?",
            (token_hash,)
        )
        row = await cursor.fetchone()
        if row and row[0] == "revoked":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your connection has been removed."
            )
    finally:
        await conn.close()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired caregiver session token"
    )


def verify_operator_token(
    authorization: Optional[str] = Header(None),
    x_operator_token: Optional[str] = Header(None)
) -> bool:
    """PR-12: Validates protected operator token for health checks."""
    raw_token = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization[7:].strip()
    elif x_operator_token:
        raw_token = x_operator_token.strip()

    if not raw_token or raw_token != settings.OPERATOR_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Operator token required"
        )
    return True
