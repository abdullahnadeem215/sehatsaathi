"""Full-Stack Frontend & Backend Integration Verification.
Tests the exact workflows executed by the React PWA frontend against the FastAPI backend:
1. Serving Frontend PWA bundle at /app
2. Patient Auto-Registration & Grounded Voice/Text Turn
3. Sudden Heart Pain Emergency & Event Bus Broadcast
4. Complete 2-Step Caregiver Pairing & Consent
5. Caregiver Scoped Dashboard & Alert Resolution
6. Remote Prescription Addition by Caregiver & Dynamic AI Grounding Retrieval
"""
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_frontend_pwa_served():
    """Verify built frontend is mounted and served at /app."""
    response = client.get("/app/")
    assert response.status_code == 200
    assert "Sehat Saathi" in response.text or "<div id=\"root\">" in response.text


def test_full_integrated_lifecycle():
    # 1. Patient Registration
    reg_res = client.post("/api/patient/register", json={"display_name": "Robert Jenkins", "preferred_script": "en"})
    assert reg_res.status_code == 200
    reg_data = reg_res.json()
    patient_token = reg_data["device_token"]
    patient_headers = {"Authorization": f"Bearer {patient_token}"}

    # 2. Grounded Question: "When should I take Metformin?"
    turn_res = client.post(
        "/api/turn",
        headers=patient_headers,
        json={"text": "When should I take Metformin?", "script": "en"}
    )
    assert turn_res.status_code == 200
    turn_data = turn_res.json()
    assert "Metformin" in turn_data["answer"]
    assert turn_data["confidence_badge"] in ["Certain", "Possibly"]
    assert turn_data["is_emergency"] is False

    # 3. Patient Pairing Key Generation
    pair_create_res = client.post("/api/pair/create", headers=patient_headers)
    assert pair_create_res.status_code == 200
    raw_key = pair_create_res.json()["key"]

    # 4. Caregiver Redeems Key
    redeem_res = client.post(
        "/api/pair/redeem",
        json={"key": raw_key, "caregiver_name": "Sarah Khan"}
    )
    assert redeem_res.status_code == 200
    pending_id = redeem_res.json()["pending_id"]

    # 5. Patient Checks Pending and Approves
    pending_list_res = client.get("/api/pair/pending", headers=patient_headers)
    assert pending_list_res.status_code == 200
    pending_items = pending_list_res.json()
    assert any(p["pending_id"] == pending_id for p in pending_items)

    decide_res = client.post(
        "/api/pair/decide",
        headers=patient_headers,
        json={"pending_id": pending_id, "approve": True}
    )
    assert decide_res.status_code == 200

    # 6. Caregiver Retrieves Session Token
    status_res = client.get(f"/api/pair/status?pending_id={pending_id}")
    assert status_res.status_code == 200
    caregiver_token = status_res.json()["session_token"]
    assert caregiver_token is not None
    caregiver_headers = {"Authorization": f"Bearer {caregiver_token}"}

    # 7. Sudden Heart Pain Emergency Triggered by Patient
    emergency_turn = client.post(
        "/api/turn",
        headers=patient_headers,
        json={"text": "I have the pain in my heart so hard", "script": "en"}
    )
    assert emergency_turn.status_code == 200
    em_data = emergency_turn.json()
    assert em_data["is_emergency"] is True
    assert em_data["ui_state"] == "emergency"
    assert "EMERGENCY" in em_data["answer"] and "alerted" in em_data["answer"]

    # 8. Caregiver Dashboard Reflects Open Alert
    dashboard_res = client.get("/api/dashboard", headers=caregiver_headers)
    assert dashboard_res.status_code == 200
    dash_data = dashboard_res.json()
    assert dash_data["summary"]["open_alerts_count"] >= 1
    open_alert = dash_data["alerts"][0]
    assert "pain in my heart" in open_alert["transcript_excerpt"].lower()

    # 9. Caregiver Marks Alert as Handled
    handled_res = client.post(f"/api/alerts/{open_alert['id']}/handled", headers=caregiver_headers)
    assert handled_res.status_code == 200

    # 10. Caregiver Adds New Remote Prescription: "Aspirin 75mg once daily with dinner"
    rx_res = client.post(
        "/api/prescriptions",
        headers=caregiver_headers,
        json={
            "medicine_name": "Aspirin",
            "dose_text": "75mg",
            "timing_text": "once daily with dinner",
            "instructions": "Take with a full glass of water"
        }
    )
    assert rx_res.status_code == 200
    rx_data = rx_res.json()
    assert rx_data["medicine_name"] == "Aspirin"

    # 11. Patient Asks about Aspirin -> Dynamically Grounded into AI Agent Knowledge!
    aspirin_turn = client.post(
        "/api/turn",
        headers=patient_headers,
        json={"text": "When do I take my Aspirin?", "script": "en"}
    )
    assert aspirin_turn.status_code == 200
    asp_data = aspirin_turn.json()
    assert "Aspirin" in asp_data["answer"] or "dinner" in asp_data["answer"].lower()
    assert asp_data["is_emergency"] is False
