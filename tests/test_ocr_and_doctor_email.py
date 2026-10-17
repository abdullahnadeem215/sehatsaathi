"""Tests for OCR Prescription Extraction and Doctor Email Consultation Service.
Verifies:
1. OCR image upload parses medicines and identifies missing timing of taking medicine.
2. Patient profile & doctor directory (personal Gmail, doctor Gmail).
3. AI drafts doctor email with health issue & active prescriptions.
4. Strict consent: Agent NEVER sends email automatically; status remains 'draft'.
5. Explicit user approval sends the email.
"""
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_ocr_prescription_missing_timing_detection():
    """Verify OCR extracts prescription and identifies missing timing."""
    # 1. Register patient
    reg = client.post("/api/patient/register", json={"display_name": "Eleanor Vance", "preferred_script": "en"})
    assert reg.status_code == 200
    token = reg.json()["device_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Upload sample prescription text as file
    prescription_sample = (
        "PRESCRIPTION\n"
        "Dr. Sarah Mitchell\n"
        "Rx: Amoxicillin 500mg\n"
        "Take with a full glass of water.\n"
    )
    files = {"file": ("prescription.txt", prescription_sample.encode("utf-8"), "text/plain")}
    res = client.post("/api/prescriptions/upload-image", headers=headers, files=files)
    assert res.status_code == 200
    data = res.json()

    assert len(data["extracted_medicines"]) > 0
    amox = data["extracted_medicines"][0]
    assert amox["medicine_name"] == "Amoxicillin"
    assert "500" in amox["dose_text"]
    # Verify missing timing detection
    assert "timing_text" in amox["missing_fields"]
    assert data["has_missing_info"] is True
    assert "timing" in data["missing_summary"].lower()


def test_ocr_different_prescriptions_not_hardcoded_amoxicillin():
    """Verify OCR extracts diverse medications accurately and does NOT default to Amoxicillin."""
    reg = client.post("/api/patient/register", json={"display_name": "Arthur Pendelton", "preferred_script": "en"})
    token = reg.json()["device_token"]
    headers = {"Authorization": f"Bearer {token}"}

    sample = (
        "CLINICAL PRESCRIPTION\n"
        "Dr. Robert Chen, MD\n"
        "Rx: Ciprofloxacin 750mg\n"
        "Rx: Atorvastatin 20mg once daily at night after dinner\n"
    )
    files = {"file": ("rx.txt", sample.encode("utf-8"), "text/plain")}
    res = client.post("/api/prescriptions/upload-image", headers=headers, files=files)
    assert res.status_code == 200
    data = res.json()

    med_names = [m["medicine_name"] for m in data["extracted_medicines"]]
    # Must NOT contain Amoxicillin
    assert "Amoxicillin" not in med_names
    assert "Ciprofloxacin" in med_names
    assert "Atorvastatin" in med_names

    cipro = next(m for m in data["extracted_medicines"] if m["medicine_name"] == "Ciprofloxacin")
    atorva = next(m for m in data["extracted_medicines"] if m["medicine_name"] == "Atorvastatin")

    assert "timing_text" in cipro["missing_fields"]
    assert "once daily" in atorva["timing_text"].lower() or "night" in atorva["timing_text"].lower() or "dinner" in atorva["timing_text"].lower()
    assert "timing_text" not in atorva["missing_fields"]
    assert data["has_missing_info"] is True


def test_doctor_profile_and_email_approval_flow():
    """Verify doctor profile setup, email drafting, and consent approval."""
    # 1. Register patient
    reg = client.post("/api/patient/register", json={"display_name": "Eleanor Vance", "preferred_script": "en"})
    token = reg.json()["device_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Update patient profile with personal Gmail & Doctor details
    profile_update = client.put(
        "/api/patient/profile",
        headers=headers,
        json={
            "email": "eleanor.vance@gmail.com",
            "doctor_name": "Dr. Sarah Mitchell",
            "doctor_email": "dr.sarah@gmail.com",
            "doctor_specialty": "Cardiology",
            "doctor_phone": "+1-555-0199"
        }
    )
    assert profile_update.status_code == 200
    profile_data = profile_update.json()
    assert profile_data["email"] == "eleanor.vance@gmail.com"
    assert profile_data["doctor_name"] == "Dr. Sarah Mitchell"
    assert profile_data["doctor_email"] == "dr.sarah@gmail.com"

    # 3. Add an active prescription
    rx_res = client.post(
        "/api/prescriptions",
        headers=headers,
        json={
            "medicine_name": "Metformin",
            "dose_text": "500mg",
            "timing_text": "every morning after breakfast",
            "instructions": "Take with water"
        }
    )
    assert rx_res.status_code == 200

    # 4. Patient reports health issue -> AI drafts doctor email
    draft_res = client.post(
        "/api/doctor/draft-email",
        headers=headers,
        json={
            "health_issue": "I have been feeling dizzy and my stomach has a burning sensation since yesterday."
        }
    )
    assert draft_res.status_code == 200
    draft_data = draft_res.json()

    # Verify STRICT RULE: Agent NEVER sends automatically (status MUST be 'draft')
    assert draft_data["status"] == "draft"
    assert draft_data["doctor_email"] == "dr.sarah@gmail.com"
    assert "Eleanor Vance" in draft_data["body"]
    assert "Metformin" in draft_data["body"]
    assert "dizzy" in draft_data["body"].lower()

    email_id = draft_data["id"]

    # 5. List emails -> shows in draft status
    list_res = client.get("/api/doctor/emails", headers=headers)
    assert list_res.status_code == 200
    assert any(e["id"] == email_id and e["status"] == "draft" for e in list_res.json())

    # 6. Patient explicitly approves sending the email
    approve_res = client.post(f"/api/doctor/emails/{email_id}/approve", headers=headers)
    assert approve_res.status_code == 200
    appr_data = approve_res.json()
    assert appr_data["status"] == "sent"
    assert "Dr. Sarah Mitchell" in appr_data["message"]
    assert appr_data["email_item"]["sent_at"] is not None
