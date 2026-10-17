"""Caregiver Dashboard and Review Queue aggregation service.
Enforces SRS FR-18, FR-23, UX-35, UX-36, UX-37 (English-only edition).
"""
from typing import Dict, Any, List, Optional
from backend.database import get_db_connection


class DashboardService:
    async def get_patient_dashboard(self, patient_id: str) -> Dict[str, Any]:
        """FR-23 / UX-35: Strictly scoped to patient_id of the authenticated caregiver token."""
        conn = await get_db_connection()
        try:
            # 1. Patient info
            p_cursor = await conn.execute(
                "SELECT display_name FROM patients WHERE id = ?",
                (patient_id,)
            )
            p_row = await p_cursor.fetchone()
            display_name = p_row[0] if p_row else "Patient"

            # 2. Alerts (UX-36: red flags at top, visually distinct)
            a_cursor = await conn.execute(
                "SELECT id, type, priority, transcript_excerpt, action_taken, created_at, handled_at FROM alerts WHERE patient_id = ? ORDER BY id DESC",
                (patient_id,)
            )
            alerts = [dict(r) for r in await a_cursor.fetchall()]
            open_alerts_count = sum(1 for a in alerts if a["handled_at"] is None)

            # 3. Review Queue (UX-37: clinician review queue)
            r_cursor = await conn.execute(
                "SELECT id, question, attempted_answer, cited_line_ids, reason, clinician_note, status, created_at FROM review_items WHERE patient_id = ? ORDER BY id DESC",
                (patient_id,)
            )
            review_queue = [dict(r) for r in await r_cursor.fetchall()]
            review_items_count = sum(1 for rq in review_queue if rq["status"] == "pending")

            # 4. Reminders & Adherence (UX-30)
            rem_cursor = await conn.execute(
                "SELECT id, patient_id, medicine_name, dose_text, timing_text, status, created_at FROM reminders WHERE patient_id = ? AND status = 'active'",
                (patient_id,)
            )
            reminders = [dict(r) for r in await rem_cursor.fetchall()]

            log_cursor = await conn.execute(
                "SELECT action FROM reminder_logs WHERE patient_id = ?",
                (patient_id,)
            )
            logs = [dict(r) for r in await log_cursor.fetchall()]
            taken_count = sum(1 for l in logs if l["action"] == "taken")
            missed_count = sum(1 for l in logs if l["action"] == "missed")
            pending_count = max(0, len(reminders) - (taken_count + missed_count))

            # 5. Appointments (FR-11)
            appt_cursor = await conn.execute(
                "SELECT id, patient_id, slot_start, status, created_at FROM appointments WHERE patient_id = ? AND status = 'booked' ORDER BY id ASC",
                (patient_id,)
            )
            appointments = [dict(r) for r in await appt_cursor.fetchall()]
            next_appointment = appointments[0]["slot_start"] if appointments else "None scheduled"

            summary = {
                "patient_display_name": display_name,
                "open_alerts_count": open_alerts_count,
                "review_items_count": review_items_count,
                "reminders_taken_today": taken_count,
                "reminders_missed_today": missed_count,
                "reminders_pending_today": pending_count,
                "next_appointment": next_appointment
            }

            return {
                "summary": summary,
                "alerts": alerts,
                "review_queue": review_queue,
                "reminders": reminders,
                "appointments": appointments
            }
        finally:
            await conn.close()

    async def add_review_note(self, review_id: int, note: str, patient_id: str) -> bool:
        """UX-37: Adds clinician note to a review queue item."""
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                "UPDATE review_items SET clinician_note = ?, status = 'reviewed' WHERE id = ? AND patient_id = ?",
                (note, review_id, patient_id)
            )
            await conn.commit()
            return cursor.rowcount > 0
        finally:
            await conn.close()


dashboard_service = DashboardService()
