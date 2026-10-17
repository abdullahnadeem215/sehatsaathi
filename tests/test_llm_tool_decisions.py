"""Tests for Agentic LLM Tool-Calling Decisions.
Verifies that the LLM acts as the decision maker to route tools:
1. alert_caregiver: triggers high-priority alert buzzer to linked caregivers
2. draft_doctor_email: creates clinical email draft with prescriptions & awaits explicit consent
3. /api/confirm: executes email dispatch or discard based on patient/caregiver decision
"""
import pytest
from backend.database import init_db_sync
from backend.services.turn_orchestrator import turn_orchestrator
from backend.services.doctor_email_service import doctor_email_service
from backend.services.pairing_service import pairing_service
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db_sync()


@pytest.mark.asyncio
async def test_llm_tool_decision_alert_caregiver():
    # Register patient and link a caregiver
    p_id, p_token = await pairing_service.register_patient_device("Alice Heart")
    raw_key, fmt_key, ttl, exp = await pairing_service.generate_pairing_key(p_id)
    success, pending_id, _ = await pairing_service.redeem_pairing_key(fmt_key, "Caregiver Bob", "127.0.0.1")
    await pairing_service.decide_link_request(pending_id, p_id, approve=True)

    # Patient asks a question with heart pain distress
    result = await turn_orchestrator.process_turn(
        patient_id=p_id,
        text="I have severe pain in my heart and difficulty breathing",
        script="en"
    )

    assert result["is_emergency"] is True
    assert result["ui_state"] == "emergency"
    assert result.get("tool_called") == "alert_caregiver"
    assert "caregiver" in result.get("emergency_action_taken", "").lower() or "buzzer" in result.get("emergency_action_taken", "").lower()
    assert result.get("alert_info") is not None


@pytest.mark.asyncio
async def test_llm_tool_decision_draft_doctor_email():
    p_id, p_token = await pairing_service.register_patient_device("Charles Smith")

    # Patient reports a non-emergency symptom or asks for doctor consultation
    result = await turn_orchestrator.process_turn(
        patient_id=p_id,
        text="I have had a mild stomach rash since yesterday, can we email the doctor?",
        script="en"
    )

    assert result["ui_state"] == "waiting_confirmation"
    assert result.get("tool_called") == "draft_doctor_email"
    assert result.get("email_draft") is not None
    draft = result["email_draft"]
    assert draft["status"] == "draft"
    assert "Dr." in draft["doctor_name"]
    assert result.get("pending_action_id") == f"email_{draft['id']}"
    assert result.get("echo_back") is not None


@pytest.mark.asyncio
async def test_doctor_email_approval_via_confirm_endpoint():
    # 1. Register patient
    p_id, p_token = await pairing_service.register_patient_device("Diana Prince")
    headers = {"Authorization": f"Bearer {p_token}"}

    # 2. Trigger turn that causes doctor email draft
    turn_res = client.post(
        "/api/turn",
        json={"text": "I feel slight dizziness after morning medicine, please consult my doctor.", "script": "en"},
        headers=headers
    )
    assert turn_res.status_code == 200
    t_data = turn_res.json()
    assert t_data["ui_state"] == "waiting_confirmation"
    assert t_data["tool_called"] == "draft_doctor_email"
    action_id = t_data["pending_action_id"]
    assert action_id.startswith("email_")

    # 3. Patient approves the email draft via /api/confirm
    confirm_res = client.post(
        "/api/confirm",
        json={"action_id": action_id, "confirmed": True},
        headers=headers
    )
    assert confirm_res.status_code == 200
    c_data = confirm_res.json()
    assert c_data["status"] == "confirmed"
    assert "successfully" in c_data["message"].lower() or "sent" in c_data["message"].lower()

    # 4. Verify email status updated to 'sent'
    email_id = int(action_id.split("_")[1])
    emails = await doctor_email_service.list_patient_emails(p_id)
    sent_item = next(e for e in emails if e["id"] == email_id)
    assert sent_item["status"] == "sent"
    assert sent_item["sent_at"] is not None
