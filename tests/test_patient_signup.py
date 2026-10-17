"""Tests for individual patient signup and database persistence.
Verifies professional signup onboarding, database storage of personal and doctor details,
and retrieval via patient profile endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_patient_signup_and_database_persistence():
    """Verify signup saves personal details & doctor details to SQLite."""
    payload = {
        "display_name": "Eleanor Vance",
        "email": "eleanor.vance@gmail.com",
        "phone": "+1 (555) 482-9901",
        "age": 68,
        "emergency_contact_name": "Thomas Vance (Son) - +1 (555) 482-9902",
        "doctor_name": "Dr. Marcus Welby",
        "doctor_email": "dr.welby@cityhealth.org",
        "doctor_specialty": "Internal Medicine",
        "doctor_phone": "+1 (555) 302-8811",
        "preferred_script": "en"
    }

    # 1. Sign up new individual user
    signup_res = client.post("/api/patient/signup", json=payload)
    assert signup_res.status_code == 200, f"Signup failed: {signup_res.text}"
    signup_data = signup_res.json()

    patient_id = signup_data["patient_id"]
    device_token = signup_data["device_token"]

    assert patient_id.startswith("pat_")
    assert len(device_token) > 20
    assert signup_data["display_name"] == "Eleanor Vance"
    assert signup_data["email"] == "eleanor.vance@gmail.com"
    assert signup_data["doctor_name"] == "Dr. Marcus Welby"
    assert signup_data["doctor_email"] == "dr.welby@cityhealth.org"

    # 2. Query patient profile with the issued device token
    headers = {"Authorization": f"Bearer {device_token}"}
    profile_res = client.get("/api/patient/profile", headers=headers)
    assert profile_res.status_code == 200
    profile = profile_res.json()

    assert profile["patient_id"] == patient_id
    assert profile["display_name"] == "Eleanor Vance"
    assert profile["email"] == "eleanor.vance@gmail.com"
    assert profile["phone"] == "+1 (555) 482-9901"
    assert profile["age"] == 68
    assert profile["emergency_contact_name"] == "Thomas Vance (Son) - +1 (555) 482-9902"
    assert profile["doctor_name"] == "Dr. Marcus Welby"
    assert profile["doctor_email"] == "dr.welby@cityhealth.org"
    assert profile["doctor_specialty"] == "Internal Medicine"
    assert profile["doctor_phone"] == "+1 (555) 302-8811"

    # 3. Verify clean slate: zero pre-populated demo reminders
    reminders_res = client.get("/api/reminders", headers=headers)
    assert reminders_res.status_code == 200
    reminders = reminders_res.json()
    assert len(reminders) == 0, "Expected clean slate without pre-populated demo reminders"

    # 4. Update profile details and verify updates persist
    update_payload = {
        "display_name": "Eleanor Vance, PhD",
        "age": 69,
        "phone": "+1 (555) 482-9909",
        "doctor_specialty": "Cardiology & Geriatrics"
    }
    update_res = client.put("/api/patient/profile", headers=headers, json=update_payload)
    assert update_res.status_code == 200
    updated_profile = update_res.json()
    assert updated_profile["display_name"] == "Eleanor Vance, PhD"
    assert updated_profile["age"] == 69
    assert updated_profile["phone"] == "+1 (555) 482-9909"
    assert updated_profile["doctor_specialty"] == "Cardiology & Geriatrics"

    # Re-fetch profile to guarantee SQLite persistence
    refetch_res = client.get("/api/patient/profile", headers=headers)
    assert refetch_res.status_code == 200
    refetched = refetch_res.json()
    assert refetched["display_name"] == "Eleanor Vance, PhD"
    assert refetched["age"] == 69
    assert refetched["phone"] == "+1 (555) 482-9909"
