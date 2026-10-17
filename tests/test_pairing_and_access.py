"""Tests for Caregiver Pairing, Patient-Controlled Consent, Scoping, and Revocation (FR-18 through FR-26, UX-39 through UX-44).
"""
import pytest
import asyncio
from backend.database import init_db_sync
from backend.services.pairing_service import pairing_service
from backend.services.dashboard_service import dashboard_service


@pytest.fixture(autouse=True)
def setup_db():
    init_db_sync()


@pytest.mark.asyncio
async def test_patient_registration_and_device_identity():
    # FR-19: Create patient record and return long random device token
    patient_id, device_token = await pairing_service.register_patient_device("Sarah Jenkins")
    assert patient_id.startswith("pat_")
    assert len(device_token) > 20

    # Verify token
    verified = await pairing_service.verify_patient_token(device_token)
    assert verified is not None
    assert verified["id"] == patient_id
    assert verified["display_name"] == "Sarah Jenkins"

    # Invalid token rejected
    bad_verify = await pairing_service.verify_patient_token("invalid-fake-token")
    assert bad_verify is None


@pytest.mark.asyncio
async def test_key_generation_and_invalidation():
    # FR-20: 8-hex character key, single-use, new key invalidates prior unused key
    patient_id, _ = await pairing_service.register_patient_device("John Doe")

    raw_key1, fmt_key1, ttl1, exp1 = await pairing_service.generate_pairing_key(patient_id)
    assert len(raw_key1) == 8
    assert "-" in fmt_key1
    assert ttl1 == 600

    # Generate second key
    raw_key2, fmt_key2, ttl2, exp2 = await pairing_service.generate_pairing_key(patient_id)
    assert raw_key1 != raw_key2

    # Attempting to redeem first key must fail because it was invalidated
    success1, _, msg1 = await pairing_service.redeem_pairing_key(raw_key1, "Caregiver 1", "127.0.0.1")
    assert success1 is False

    # Attempting to redeem second key should succeed
    success2, pending_id, msg2 = await pairing_service.redeem_pairing_key(fmt_key2, "Caregiver 1", "127.0.0.1")
    assert success2 is True
    assert pending_id is not None


@pytest.mark.asyncio
async def test_pairing_consent_flow_and_token_issuance():
    # FR-21, FR-22, UX-42: Caregiver redeems -> pending consent -> patient approves -> session token issued
    patient_id, _ = await pairing_service.register_patient_device("Alice")
    raw_key, _, _, _ = await pairing_service.generate_pairing_key(patient_id)

    # Caregiver redeems key (with lowercase and dashes ignored)
    dirty_key = f"{raw_key[:4].lower()} - {raw_key[4:].lower()}"
    success, pending_id, _ = await pairing_service.redeem_pairing_key(dirty_key, "Bob", "192.168.1.50")
    assert success is True

    # Patient checks pending requests
    pending = await pairing_service.get_pending_requests(patient_id)
    assert len(pending) > 0
    assert pending[0]["pending_id"] == pending_id
    assert pending[0]["caregiver_name"] == "Bob"

    # Patient approves
    approved, _ = await pairing_service.decide_link_request(patient_id, pending_id, approve=True)
    assert approved is True

    # Caregiver checks status and retrieves token
    status_str, token, name, _ = await pairing_service.check_pairing_status(pending_id)
    assert status_str == "approved"
    assert token is not None
    assert len(token) >= 32  # At least 128-bit secret
    assert name == "Bob"

    # Verify caregiver session token resolves to patient Alice (FR-23)
    cg_info = await pairing_service.verify_caregiver_token(token)
    assert cg_info is not None
    assert cg_info["patient_id"] == patient_id
    assert cg_info["caregiver_name"] == "Bob"


@pytest.mark.asyncio
async def test_caregiver_scoping_isolation():
    # FR-23: Caregiver A cannot read Patient B's data
    patient_a, _ = await pairing_service.register_patient_device("Patient A")
    patient_b, _ = await pairing_service.register_patient_device("Patient B")

    # Link caregiver Bob to Patient A
    raw_key, _, _, _ = await pairing_service.generate_pairing_key(patient_a)
    _, pending_id, _ = await pairing_service.redeem_pairing_key(raw_key, "Bob", "10.0.0.1")
    await pairing_service.decide_link_request(patient_a, pending_id, approve=True)
    _, token_a, _, _ = await pairing_service.check_pairing_status(pending_id)

    # Bob accesses dashboard -> must strictly receive Patient A's dashboard
    cg_context = await pairing_service.verify_caregiver_token(token_a)
    dashboard_data = await dashboard_service.get_patient_dashboard(cg_context["patient_id"])
    assert dashboard_data["summary"]["patient_display_name"] == "Patient A"
    assert cg_context["patient_id"] != patient_b


@pytest.mark.asyncio
async def test_caregiver_revocation():
    # FR-24 / UX-44: Patient revokes caregiver; token rejected on next request
    patient_id, _ = await pairing_service.register_patient_device("Charlie")
    raw_key, _, _, _ = await pairing_service.generate_pairing_key(patient_id)
    _, pending_id, _ = await pairing_service.redeem_pairing_key(raw_key, "David", "10.0.0.2")
    await pairing_service.decide_link_request(patient_id, pending_id, approve=True)
    _, session_token, _, _ = await pairing_service.check_pairing_status(pending_id)

    # Verify token active
    assert await pairing_service.verify_caregiver_token(session_token) is not None

    # Patient lists and revokes link
    links = await pairing_service.list_patient_links(patient_id)
    assert len(links) == 1
    link_id = links[0]["id"]

    revoked = await pairing_service.revoke_caregiver_link(patient_id, link_id)
    assert revoked is True

    # Next request with that session token is immediately rejected
    assert await pairing_service.verify_caregiver_token(session_token) is None
