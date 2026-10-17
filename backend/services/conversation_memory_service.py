"""Conversation Memory Service.
Provides persistent multi-turn memory for the AI Agent, allowing the agent
to be aware of prior conversations, questions asked, health issues reported,
and medication intake events.
"""
import json
import logging
from typing import List, Dict, Any, Optional
from backend.database import get_db_connection
from backend.utils import utc_now_iso

logger = logging.getLogger("sehat_saathi.memory")


class ConversationMemoryService:
    async def add_memory(
        self,
        patient_id: str,
        user_query: str,
        assistant_response: str,
        intent: str = "qa",
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Stores a conversation turn in long-term memory."""
        conn = await get_db_connection()
        try:
            meta_json = json.dumps(metadata or {})
            cursor = await conn.execute(
                """
                INSERT INTO conversation_memories (patient_id, user_query, assistant_response, intent, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (patient_id, user_query, assistant_response, intent, meta_json, utc_now_iso())
            )
            await conn.commit()
            return cursor.lastrowid
        finally:
            await conn.close()

    async def get_recent_memories(self, patient_id: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Retrieves the recent conversation turns in chronological order."""
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                """
                SELECT id, user_query, assistant_response, intent, metadata, created_at
                FROM conversation_memories
                WHERE patient_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (patient_id, limit)
            )
            rows = await cursor.fetchall()
            # Return in chronological order
            return [dict(r) for r in reversed(rows)]
        finally:
            await conn.close()

    async def get_memory_context_string(self, patient_id: str, limit: int = 5) -> str:
        """Formats recent conversation history and today's medication adherence records
        into an awareness block for the LLM prompt.
        """
        memories = await self.get_recent_memories(patient_id, limit=limit)
        adherence_logs = await self._get_recent_adherence_records(patient_id, limit=4)

        if not memories and not adherence_logs:
            return ""

        parts = []
        if memories:
            parts.append("--- PREVIOUS CONVERSATION MEMORY (AWARENESS OF PRIOR TURNS) ---")
            for idx, m in enumerate(memories, 1):
                time_str = m.get("created_at", "")[:19]
                parts.append(f"Turn {idx} [{time_str}]:")
                parts.append(f"Patient: {m['user_query']}")
                parts.append(f"Assistant: {m['assistant_response']}")

        if adherence_logs:
            parts.append("\n--- TODAY'S MEDICATION ADHERENCE RECORDS & LOGS ---")
            for a in adherence_logs:
                med = a.get("medicine_name", "Medicine")
                dose = a.get("dose_text", "")
                timing = a.get("timing_text", "")
                action = str(a.get("action", "unknown")).upper()
                intake_time = a.get("actual_intake_time") or a.get("logged_at") or ""
                note = a.get("intake_notes") or ""
                note_str = f" ({note})" if note else ""
                parts.append(f"• {med} {dose} [{timing}]: {action} at {intake_time[:19]}{note_str}")

        parts.append("------------------------------------------------------------------")
        return "\n".join(parts)

    async def _get_recent_adherence_records(self, patient_id: str, limit: int = 4) -> List[Dict[str, Any]]:
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                """
                SELECT l.id, l.reminder_id, r.medicine_name, r.dose_text, r.timing_text,
                       l.action, l.scheduled_time, l.actual_intake_time, l.intake_notes, l.logged_at
                FROM reminder_logs l
                LEFT JOIN reminders r ON l.reminder_id = r.id
                WHERE l.patient_id = ?
                ORDER BY l.id DESC
                LIMIT ?
                """,
                (patient_id, limit)
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await conn.close()


conversation_memory_service = ConversationMemoryService()
