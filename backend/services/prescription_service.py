"""Prescription management and dynamic discharge summary synchronization service.
Allows Caregivers and Patients to easily add new prescriptions, which automatically:
1. Creates active scheduled medicine reminders.
2. Dynamically indexes the new medication into summary_lines for instant AI Grounding.
3. Broadcasts real-time SSE updates across Patient and Caregiver PWAs.
"""
from typing import List, Dict, Any, Optional
from backend.database import get_db_connection
from backend.utils import utc_now_iso
from backend.services.event_bus import event_bus


class PrescriptionService:
    async def add_prescription(
        self,
        patient_id: str,
        added_by: str,
        author_name: str,
        medicine_name: str,
        dose_text: str,
        timing_text: str,
        instructions: Optional[str] = None
    ) -> Dict[str, Any]:
        conn = await get_db_connection()
        try:
            now_iso = utc_now_iso()
            # 1. Insert into prescriptions table
            cur = await conn.execute(
                """
                INSERT INTO prescriptions (
                    patient_id, added_by, author_name, medicine_name, dose_text, timing_text, instructions, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (patient_id, added_by, author_name, medicine_name, dose_text, timing_text, instructions or "", now_iso)
            )
            rx_id = cur.lastrowid

            # 2. Automatically create an active reminder for this prescription
            await conn.execute(
                """
                INSERT INTO reminders (patient_id, medicine_name, dose_text, timing_text, status, created_at)
                VALUES (?, ?, ?, ?, 'active', ?)
                """,
                (patient_id, medicine_name, dose_text, timing_text, now_iso)
            )

            # 3. Dynamically insert a new numbered line into the patient's summary_lines for AI grounding
            # Find the patient's discharge summary id
            s_cursor = await conn.execute(
                "SELECT id FROM discharge_summaries WHERE patient_id = ? LIMIT 1",
                (patient_id,)
            )
            s_row = await s_cursor.fetchone()
            summary_id = s_row[0] if s_row else "summary-synth-01"

            # Determine next line ID (e.g. L9, L10)
            cnt_cursor = await conn.execute("SELECT COUNT(*) FROM summary_lines WHERE summary_id = ?", (summary_id,))
            line_count = (await cnt_cursor.fetchone())[0]
            new_line_id = f"L{line_count + 1}"

            extra_inst = f" {instructions.strip()}." if instructions and instructions.strip() else ""
            line_text = f"Take Tablet {medicine_name} {dose_text} {timing_text}.{extra_inst}"

            await conn.execute(
                """
                INSERT INTO summary_lines (summary_id, line_id, text)
                VALUES (?, ?, ?)
                """,
                (summary_id, new_line_id, line_text)
            )
            await conn.commit()

            result = {
                "id": rx_id,
                "patient_id": patient_id,
                "added_by": added_by,
                "author_name": author_name,
                "medicine_name": medicine_name,
                "dose_text": dose_text,
                "timing_text": timing_text,
                "instructions": instructions,
                "grounded_line_id": new_line_id,
                "status": "active",
                "created_at": now_iso
            }

            # 4. Real-time free broadcast to connected devices
            await event_bus.broadcast_to_caregivers(
                patient_id=patient_id,
                event_type="prescription_updated",
                payload=result
            )
            await event_bus.broadcast_to_patient(
                patient_id=patient_id,
                event_type="prescription_updated",
                payload=result
            )

            return result
        finally:
            await conn.close()

    async def get_active_prescriptions(self, patient_id: str) -> List[Dict[str, Any]]:
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                """
                SELECT id, patient_id, added_by, author_name, medicine_name, dose_text, timing_text, instructions, status, created_at
                FROM prescriptions
                WHERE patient_id = ? AND status = 'active'
                ORDER BY id DESC
                """,
                (patient_id,)
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def deactivate_prescription(self, patient_id: str, prescription_id: int) -> bool:
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                "UPDATE prescriptions SET status = 'inactive' WHERE id = ? AND patient_id = ?",
                (prescription_id, patient_id)
            )
            await conn.commit()
            return cursor.rowcount > 0
        finally:
            await conn.close()


prescription_service = PrescriptionService()
