"""End-to-end API Integration tests for FastAPI endpoints.
Tests SRS Section 7.2 & 7.3, PR-07, PR-12.
"""
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings

client = TestClient(app)


def test_root_and_healthz():
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["status"] == "online"

    h = client.get("/healthz")
    assert h.status_code == 200
    assert h.json()["status"] == "ok"


def test_patient_registration_and_turn_flow():
    # 1. Register patient
    reg_resp = client.post("/api/patient/register", json={"display_name": "Edward Wilson"})
    assert reg_resp.status_code == 200
    reg_data = reg_resp.json()
    patient_id = reg_data["patient_id"]
    token = reg_data["device_token"]

    headers = {"Authorization": f"Bearer {token}"}

    # 2. Ask grounded question
    turn_resp = client.post(
        "/api/turn",
        json={"text": "When should I take Metformin?", "script": "en"},
        headers=headers
    )
    assert turn_resp.status_code == 200
    t_data = turn_resp.json()
    assert t_data["ui_state"] == "speaking"
    assert "Metformin" in t_data["answer"]
    assert "L2" in t_data["cited_line_ids"]
    assert t_data["confidence_badge"] == "Certain"
    # PR-07: Check no provider name exposed to client
    assert "amd" not in t_data["answer"].lower()
    assert "huggingface" not in t_data["answer"].lower()

    # 3. Emergency red flag trigger
    rf_resp = client.post(
        "/api/turn",
        json={"text": "I have severe chest pain and pressure", "script": "en"},
        headers=headers
    )
    assert rf_resp.status_code == 200
    rf_data = rf_resp.json()
    assert rf_data["is_emergency"] is True
    assert rf_data["ui_state"] == "emergency"
    assert "emergency" in rf_data["answer"].lower()


def test_full_caregiver_pairing_and_dashboard_flow():
    # 1. Register patient
    reg_resp = client.post("/api/patient/register", json={"display_name": "Mary Johnson"})
    patient_token = reg_resp.json()["device_token"]
    p_headers = {"Authorization": f"Bearer {patient_token}"}

    # 2. Patient generates pairing key
    pair_resp = client.post("/api/pair/create", headers=p_headers)
    assert pair_resp.status_code == 200
    key_info = pair_resp.json()
    raw_key = key_info["key"]
    formatted_key = key_info["formatted_key"]

    # 3. Caregiver redeems key with name
    redeem_resp = client.post(
        "/api/pair/redeem",
        json={"key": formatted_key, "caregiver_name": "Dr. Davis"}
    )
    assert redeem_resp.status_code == 200
    pending_id = redeem_resp.json()["pending_id"]

    # 4. Patient polls pending requests
    pending_resp = client.get("/api/pair/pending", headers=p_headers)
    assert pending_resp.status_code == 200
    pending_list = pending_resp.json()
    assert any(p["pending_id"] == pending_id for p in pending_list)

    # 5. Patient approves link
    decide_resp = client.post(
        "/api/pair/decide",
        json={"pending_id": pending_id, "approve": True},
        headers=p_headers
    )
    assert decide_resp.status_code == 200
    assert decide_resp.json()["status"] == "approved"

    # 6. Caregiver polls status and retrieves session token
    status_resp = client.get(f"/api/pair/status?pending_id={pending_id}")
    assert status_resp.status_code == 200
    cg_token = status_resp.json()["session_token"]
    assert cg_token is not None

    cg_headers = {"Authorization": f"Bearer {cg_token}"}

    # 7. Caregiver accesses dashboard
    dash_resp = client.get("/api/dashboard", headers=cg_headers)
    assert dash_resp.status_code == 200
    dash_data = dash_resp.json()
    assert dash_data["summary"]["patient_display_name"] == "Mary Johnson"

    # 8. Patient revokes caregiver link
    links_resp = client.get("/api/pair/links", headers=p_headers)
    links = links_resp.json()
    link_id = links[0]["id"]

    revoke_resp = client.delete(f"/api/pair/links/{link_id}", headers=p_headers)
    assert revoke_resp.status_code == 200

    # 9. Next caregiver request is immediately rejected with 403 (UX-44)
    dash_after = client.get("/api/dashboard", headers=cg_headers)
    assert dash_after.status_code == 403
    assert "Your connection has been removed" in dash_after.json()["detail"]


def test_operator_health_endpoint_auth():
    # PR-12: Requires OPERATOR_TOKEN
    unauth = client.get("/internal/health")
    assert unauth.status_code == 403

    auth = client.get(
        "/internal/health",
        headers={"Authorization": f"Bearer {settings.OPERATOR_TOKEN}"}
    )
    assert auth.status_code == 200
    data = auth.json()
    assert data["status"] == "healthy"
    assert "llm" in data["capabilities"]
    assert "stt" in data["capabilities"]
    assert "tts" in data["capabilities"]
