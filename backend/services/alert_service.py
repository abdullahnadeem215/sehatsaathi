"""Alert fan-out and management service.
Enforces SRS FR-13, FR-26, UX-17, UX-36.
"""
from typing import List, Optional, Dict, Any
import aiosqlite
from backend.database import get_db_connection
from backend.utils import utc_now_iso
from backend.services.event_bus import event_bus


class AlertService:
    async def create_and_fanout_alert(
        self,
        patient_id: str,
        alert_type: str,
        priority: str,
        transcript_excerpt: str,
        action_taken: str
    ) -> int:
        """FR-26: Persists alert and delivers to all active linked caregivers."""
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                """
                INSERT INTO alerts (patient_id, type, priority, transcript_excerpt, action_taken, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (patient_id, alert_type, priority, transcript_excerpt, action_taken, utc_now_iso())
            )
            alert_id = cursor.lastrowid
            
            # Fetch patient name for friendly buzzer announcement
            p_cursor = await conn.execute("SELECT display_name FROM patients WHERE id = ?", (patient_id,))
            p_row = await p_cursor.fetchone()
            patient_name = p_row[0] if p_row else "Patient"

            await conn.commit()

            # Real-time free SSE broadcast to linked caregiver PWAs for Emergency Siren / Buzzer
            await event_bus.broadcast_to_caregivers(
                patient_id=patient_id,
                event_type="emergency_buzzer",
                payload={
                    "alert_id": alert_id,
                    "patient_id": patient_id,
                    "patient_name": patient_name,
                    "alert_type": alert_type,
                    "priority": priority,
                    "transcript_excerpt": transcript_excerpt,
                    "action_taken": action_taken,
                    "sound_buzzer": True
                }
            )
            return alert_id
        finally:
            await conn.close()

    async def get_patient_alerts(self, patient_id: str, active_only: bool = False) -> List[Dict[str, Any]]:
        conn = await get_db_connection()
        try:
            query = "SELECT * FROM alerts WHERE patient_id = ?"
            params = [patient_id]
            if active_only:
                query += " AND handled_at IS NULL"
            query += " ORDER BY id DESC"
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            await conn.close()

    async def mark_handled(self, alert_id: int, patient_id: Optional[str] = None) -> bool:
        """UX-36: Caregiver or patient marks an alert as handled."""
        conn = await get_db_connection()
        try:
            now_iso = utc_now_iso()
            if patient_id:
                cursor = await conn.execute(
                    "UPDATE alerts SET handled_at = ? WHERE id = ? AND (patient_id = ? OR patient_id IS NULL)",
                    (now_iso, alert_id, patient_id)
                )
            else:
                cursor = await conn.execute(
                    "UPDATE alerts SET handled_at = ? WHERE id = ?",
                    (now_iso, alert_id)
                )
            await conn.commit()
            return True
        finally:
            await conn.close()


alert_service = AlertService()
