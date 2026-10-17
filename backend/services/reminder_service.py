"""Medicine reminder and adherence tracking service.
Enforces SRS FR-06, FR-07, FR-08, FR-09, UX-14, UX-30 (English-only edition).
"""
import uuid
import json
from typing import List, Dict, Any, Optional, Tuple
from backend.database import get_db_connection
from backend.utils import utc_now_iso


class ReminderService:
    async def prepare_reminder_confirmation(
        self,
        patient_id: str,
        medicine_name: str,
        dose_text: str,
        timing_text: str
    ) -> Tuple[str, str]:
        """FR-06 / UX-14: Echo-back pattern before saving. Dose text must be preserved exactly."""
        action_id = f"act_{uuid.uuid4().hex[:12]}"
        # Exact dose preservation rule FR-08
        echo_text = f"I heard: {medicine_name} {dose_text} {timing_text}. Is that correct?"

        payload = {
            "medicine_name": medicine_name,
            "dose_text": dose_text,
            "timing_text": timing_text
        }

        conn = await get_db_connection()
        try:
            await conn.execute(
                """
                INSERT INTO pending_actions (id, patient_id, action_type, action_data, echo_back_text, created_at, status)
                VALUES (?, ?, 'reminder', ?, ?, ?, 'pending')
                """,
                (action_id, patient_id, json.dumps(payload), echo_text, utc_now_iso())
            )
            await conn.commit()
            return action_id, echo_text
        finally:
            await conn.close()

    async def execute_confirmed_reminder(self, action_id: str, patient_id: str) -> Optional[Dict[str, Any]]:
        """FR-16: Saves confirmed reminder to database."""
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
                INSERT INTO reminders (patient_id, medicine_name, dose_text, timing_text, status, created_at)
                VALUES (?, ?, ?, ?, 'active', ?)
                """,
                (patient_id, data["medicine_name"], data["dose_text"], data["timing_text"], utc_now_iso())
            )
            reminder_id = cur.lastrowid

            await conn.execute(
                "UPDATE pending_actions SET status = 'confirmed' WHERE id = ?",
                (action_id,)
            )
            await conn.commit()
            data["id"] = reminder_id
            return data
        finally:
            await conn.close()

    async def reject_pending_action(self, action_id: str, patient_id: str) -> bool:
        """UX-15: 'No' returns to question flow without error state."""
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                "UPDATE pending_actions SET status = 'rejected' WHERE id = ? AND patient_id = ?",
                (action_id, patient_id)
            )
            await conn.commit()
            return cursor.rowcount > 0
        finally:
            await conn.close()

    async def get_patient_reminders(self, patient_id: str) -> List[Dict[str, Any]]:
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                "SELECT id, patient_id, medicine_name, dose_text, timing_text, status, created_at FROM reminders WHERE patient_id = ? AND status = 'active'",
                (patient_id,)
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def record_adherence_action(
        self,
        reminder_id: int,
        patient_id: str,
        action: str,  # 'taken', 'snoozed', 'missed'
        scheduled_time: Optional[str] = None,
        actual_intake_time: Optional[str] = None,
        intake_notes: Optional[str] = None
    ) -> bool:
        """FR-09 / UX-30: Records taken/snoozed/missed actions for adherence logs."""
        conn = await get_db_connection()
        try:
            sched_time = scheduled_time or utc_now_iso()
            intake_time = actual_intake_time or utc_now_iso()
            await conn.execute(
                """
                INSERT INTO reminder_logs (reminder_id, patient_id, scheduled_time, action, actual_intake_time, intake_notes, logged_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (reminder_id, patient_id, sched_time, action, intake_time, intake_notes, utc_now_iso())
            )
            await conn.commit()

            # Broadcast real-time adherence update to linked caregiver PWAs
            try:
                from backend.services.event_bus import event_bus
                await event_bus.broadcast_to_caregivers(
                    patient_id=patient_id,
                    event_type="adherence_updated",
                    payload={"reminder_id": reminder_id, "action": action, "actual_intake_time": intake_time}
                )
            except Exception:
                pass

            return True
        finally:
            await conn.close()

    async def record_natural_intake(
        self,
        patient_id: str,
        medicine_name: Optional[str] = None,
        time_offset_minutes: int = 0,
        intake_note: Optional[str] = None
    ) -> Dict[str, Any]:
        """Manages natural language responses when a patient says they took their medicine.
        Computes the actual intake timestamp from time_offset_minutes (e.g. 60 for '1 hour ago').
        """
        from datetime import datetime, timedelta, timezone

        reminders = await self.get_patient_reminders(patient_id)
        matched_reminder = None

        if medicine_name and reminders:
            name_lower = medicine_name.lower().strip()
            for r in reminders:
                if name_lower in r["medicine_name"].lower() or r["medicine_name"].lower() in name_lower:
                    matched_reminder = r
                    break

        # Fallback to the first active reminder if no specific medicine name matched
        if not matched_reminder and reminders:
            matched_reminder = reminders[0]

        # Calculate actual intake time
        now_utc = datetime.now(timezone.utc)
        intake_dt = now_utc - timedelta(minutes=max(0, time_offset_minutes))
        actual_intake_iso = intake_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Friendly time description
        if time_offset_minutes >= 55:
            hours = max(1, round(time_offset_minutes / 60))
            time_desc = f"about {hours} hour{'s' if hours > 1 else ''} ago"
        elif time_offset_minutes > 0:
            time_desc = f"about {time_offset_minutes} minutes ago"
        else:
            time_desc = "just now"

        med_name = matched_reminder["medicine_name"] if matched_reminder else (medicine_name or "your medication")
        dose_text = matched_reminder["dose_text"] if matched_reminder else ""
        timing_text = matched_reminder["timing_text"] if matched_reminder else ""
        reminder_id = matched_reminder["id"] if matched_reminder else 1

        full_note = intake_note or f"Patient reported taking {med_name} {time_desc}"

        await self.record_adherence_action(
            reminder_id=reminder_id,
            patient_id=patient_id,
            action="taken",
            scheduled_time=timing_text or utc_now_iso(),
            actual_intake_time=actual_intake_iso,
            intake_notes=full_note
        )

        confirm_msg = f"I've recorded that you took your {med_name} {dose_text} {time_desc}. Great job staying on track with your routine!"

        return {
            "status": "success",
            "medicine_name": med_name,
            "dose_text": dose_text,
            "timing_text": timing_text,
            "time_offset_minutes": time_offset_minutes,
            "time_desc": time_desc,
            "actual_intake_time": actual_intake_iso,
            "message": confirm_msg
        }

    async def get_due_reminder_prompt(self, patient_id: str) -> Dict[str, Any]:
        """Checks if a medicine is scheduled and returns a gentle prompt asking if the patient took it."""
        reminders = await self.get_patient_reminders(patient_id)
        if not reminders:
            return {"has_due_reminder": False, "reminder": None, "prompt_text": None}

        # Check which reminders have not been logged as taken today
        conn = await get_db_connection()
        try:
            today_prefix = utc_now_iso()[:10]  # YYYY-MM-DD
            cursor = await conn.execute(
                """
                SELECT reminder_id FROM reminder_logs
                WHERE patient_id = ? AND action = 'taken' AND logged_at >= ?
                """,
                (patient_id, today_prefix)
            )
            taken_ids = {row[0] for row in await cursor.fetchall()}

            for r in reminders:
                if r["id"] not in taken_ids:
                    return {
                        "has_due_reminder": True,
                        "reminder": r,
                        "prompt_text": f"Did you take your {r['medicine_name']} {r['dose_text']} scheduled for {r['timing_text']}?"
                    }

            # If all taken today, return the first as a reference without active alert
            return {
                "has_due_reminder": False,
                "all_taken_today": True,
                "reminder": reminders[0],
                "prompt_text": f"All scheduled doses taken for today!"
            }
        finally:
            await conn.close()


reminder_service = ReminderService()
