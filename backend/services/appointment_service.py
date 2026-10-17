"""Mock clinic calendar and appointment booking service.
Enforces SRS FR-10, FR-11, UX-14 (English-only edition).
"""
import uuid
import json
from typing import List, Dict, Any, Optional, Tuple
from backend.database import get_db_connection
from backend.utils import utc_now_iso

# Mock calendar slots (FR-10: speaks no more than three at a time)
MOCK_SLOTS = [
    {"slot_id": "slot_01", "slot_start": "2026-10-16 10:00 AM", "display_text": "Tomorrow, 10:00 AM with Dr. Sarah", "available": True},
    {"slot_id": "slot_02", "slot_start": "2026-10-16 02:00 PM", "display_text": "Tomorrow, 2:00 PM with Dr. Sarah", "available": True},
    {"slot_id": "slot_03", "slot_start": "2026-10-17 11:00 AM", "display_text": "Saturday, 11:00 AM with Dr. Sarah", "available": True},
]


class AppointmentService:
    def get_available_slots(self, limit: int = 3) -> List[Dict[str, Any]]:
        """FR-10: Returns available slots, maximum 3."""
        return MOCK_SLOTS[:limit]

    async def prepare_booking_confirmation(
        self,
        patient_id: str,
        slot_text: str
    ) -> Tuple[str, str]:
        """UX-14: Echo-back before booking."""
        action_id = f"act_{uuid.uuid4().hex[:12]}"
        echo_text = f"I heard: Book appointment for {slot_text}. Is that correct?"

        payload = {"slot_start": slot_text}

        conn = await get_db_connection()
        try:
            await conn.execute(
                """
                INSERT INTO pending_actions (id, patient_id, action_type, action_data, echo_back_text, created_at, status)
                VALUES (?, ?, 'appointment', ?, ?, ?, 'pending')
                """,
                (action_id, patient_id, json.dumps(payload), echo_text, utc_now_iso())
            )
            await conn.commit()
            return action_id, echo_text
        finally:
            await conn.close()

    async def execute_confirmed_booking(self, action_id: str, patient_id: str) -> Optional[Dict[str, Any]]:
        """FR-11: Saves booked appointment to database."""
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                "SELECT action_data, status FROM pending_actions WHERE id = ? AND patient_id = ?",
                (action_id, patient_id)
            )
            row = await cursor.fetchone()
            if not row or row[1] != "pending":
                return None

            data = json.loads(row[0])
            cur = await conn.execute(
                """
                INSERT INTO appointments (patient_id, slot_start, status, created_at)
                VALUES (?, ?, 'booked', ?)
                """,
                (patient_id, data["slot_start"], utc_now_iso())
            )
            appt_id = cur.lastrowid

            await conn.execute(
                "UPDATE pending_actions SET status = 'confirmed' WHERE id = ?",
                (action_id,)
            )
            await conn.commit()
            data["id"] = appt_id
            return data
        finally:
            await conn.close()

    async def get_patient_appointments(self, patient_id: str) -> List[Dict[str, Any]]:
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                "SELECT id, patient_id, slot_start, status, created_at FROM appointments WHERE patient_id = ? AND status = 'booked' ORDER BY id DESC",
                (patient_id,)
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await conn.close()


appointment_service = AppointmentService()
