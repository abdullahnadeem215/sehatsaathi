"""Tests for Medication Due Reminders, Natural Intake Parsing, and Persistent Agent Memory.
Verifies:
1. Natural intake offset parsing (e.g. "1 hour ago", offset=60).
2. Medication adherence logging with actual intake timestamps.
3. Due reminder prompt detection.
4. Conversation memory persistence and awareness across turns.
5. Turn orchestrator end-to-end multi-turn query awareness.
6. Patient API endpoints for due reminders, intake, and memories.
"""
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import init_db_sync, get_db_connection
from backend.services.reminder_service import reminder_service
from backend.services.conversation_memory_service import conversation_memory_service
from backend.services.turn_orchestrator import turn_orchestrator
from backend.services.pairing_service import pairing_service


@pytest.fixture(autouse=True)
def setup_database():
    init_db_sync()


@pytest.mark.asyncio
async def test_record_natural_intake_offset_calculation():
    # Register a patient
    patient_id, _ = await pairing_service.register_patient_device("Test Memory Patient")
    
    # Record intake 60 minutes ago
    res = await reminder_service.record_natural_intake(
        patient_id=patient_id,
        medicine_name="Metformin",
        time_offset_minutes=60,
        intake_note="I've took this 1 hour till now"
    )

    assert res["status"] == "success"
    assert "Metformin" in res["medicine_name"]
    assert res["time_offset_minutes"] == 60
    assert "1 hour" in res["time_desc"]
    assert "actual_intake_time" in res
    assert "recorded that you took" in res["message"]

    # Verify database log
    conn = await get_db_connection()
    try:
        cursor = await conn.execute(
            "SELECT action, actual_intake_time, intake_notes FROM reminder_logs WHERE patient_id = ? ORDER BY id DESC LIMIT 1",
            (patient_id,)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["action"] == "taken"
        assert row["actual_intake_time"] is not None
        assert "1 hour" in row["intake_notes"]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_get_due_reminder_prompt():
    patient_id, _ = await pairing_service.register_patient_device("Due Prompt Patient")

    # Patient has default reminders from synthetic data or add one
    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            INSERT INTO reminders (patient_id, medicine_name, dose_text, timing_text, status, created_at)
            VALUES (?, 'Lisinopril', '10mg', '8:00 AM after breakfast', 'active', '2026-10-17T08:00:00Z')
            """,
            (patient_id,)
        )
        await conn.commit()
    finally:
        await conn.close()

    # Before taking dose, it should show as due
    due_res = await reminder_service.get_due_reminder_prompt(patient_id)
    assert due_res["has_due_reminder"] is True
    assert "Lisinopril" in due_res["prompt_text"]

    # Now record it as taken
    await reminder_service.record_natural_intake(
        patient_id=patient_id,
        medicine_name="Lisinopril",
        time_offset_minutes=0
    )

    # Now verify it's marked taken today
    due_res_after = await reminder_service.get_due_reminder_prompt(patient_id)
    assert due_res_after["has_due_reminder"] is False


@pytest.mark.asyncio
async def test_conversation_memory_persistence():
    patient_id, _ = await pairing_service.register_patient_device("Memory Recall Patient")

    # Add memory turns
    m_id1 = await conversation_memory_service.add_memory(
        patient_id=patient_id,
        user_query="I took my Metformin 1 hour ago",
        assistant_response="I've recorded that you took your Metformin about 1 hour ago.",
        intent="adherence"
    )
    assert m_id1 > 0

    m_id2 = await conversation_memory_service.add_memory(
        patient_id=patient_id,
        user_query="Can I drink warm water with it?",
        assistant_response="Yes, take your Metformin with a full glass of water or food.",
        intent="qa"
    )
    assert m_id2 > 0

    # Retrieve memories
    memories = await conversation_memory_service.get_recent_memories(patient_id, limit=5)
    assert len(memories) >= 2
    assert memories[-1]["user_query"] == "Can I drink warm water with it?"

    # Context string formatting
    ctx_str = await conversation_memory_service.get_memory_context_string(patient_id)
    assert "PREVIOUS CONVERSATION MEMORY" in ctx_str
    assert "Metformin 1 hour ago" in ctx_str


@pytest.mark.asyncio
async def test_turn_orchestrator_natural_intake_and_memory_recall():
    patient_id, _ = await pairing_service.register_patient_device("Full Turn Patient")

    # Turn 1: Patient reports taking medicine 1 hour ago
    turn1 = await turn_orchestrator.process_turn(
        patient_id=patient_id,
        text="I've took this 1 hour till now"
    )
    assert turn1["tool_called"] == "record_medication_intake"
    assert "1 hour ago" in turn1["answer"]

    # Turn 2: Patient asks if they took their medicine
    turn2 = await turn_orchestrator.process_turn(
        patient_id=patient_id,
        text="Did I take my medicine?"
    )
    assert "hour ago" in turn2["answer"] or "Metformin" in turn2["answer"]

    # Verify conversation memory contains both turns
    memories = await conversation_memory_service.get_recent_memories(patient_id)
    assert len(memories) >= 2


def test_api_due_reminders_and_intake_endpoints():
    client = TestClient(app)

    # Register patient
    reg = client.post("/api/patient/register", json={"display_name": "API Patient"})
    assert reg.status_code == 200
    token = reg.json()["device_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Check due reminders endpoint
    due_res = client.get("/api/reminders/due", headers=headers)
    assert due_res.status_code == 200

    # 2. Record natural intake endpoint with 60 min offset
    intake_res = client.post(
        "/api/reminders/intake",
        headers=headers,
        json={
            "medicine_name": "Metformin",
            "time_offset_minutes": 60,
            "intake_note": "Taken 1 hour ago"
        }
    )
    assert intake_res.status_code == 200
    intake_data = intake_res.json()
    assert intake_data["status"] == "success"
    assert "actual_intake_time" in intake_data

    # 3. Check memory endpoint
    mem_res = client.get("/api/patient/memory", headers=headers)
    assert mem_res.status_code == 200
    assert "memories" in mem_res.json()
