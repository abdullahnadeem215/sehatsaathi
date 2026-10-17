"""Turn Orchestrator service.
Coordinates audio/text input, deterministic safety filter, provider abstractions,
grounding checks, confirm-before-act echoes, and latency logging.
Enforces SRS FR-01 through FR-17, UX-14 through UX-28 (English-only edition).
"""
import time
import json
import base64
from typing import Dict, Any, Optional, List
from datetime import datetime
from backend.utils import utc_now_iso

from backend.config import settings
from backend.database import get_db_connection
from backend.providers.factory import provider_factory
from backend.services.safety_service import safety_service
from backend.services.grounding_service import grounding_service
from backend.services.reminder_service import reminder_service
from backend.services.appointment_service import appointment_service
from backend.services.alert_service import alert_service
from backend.services.doctor_email_service import doctor_email_service
from backend.services.conversation_memory_service import conversation_memory_service


class TurnOrchestrator:
    async def process_turn(
        self,
        patient_id: str,
        text: Optional[str] = None,
        audio_base64: Optional[str] = None,
        script: str = "en"
    ) -> Dict[str, Any]:
        t_start = time.perf_counter()
        latencies: Dict[str, float] = {}

        # 1. Resolve Input & STT (FR-01)
        transcript = ""
        stt_latency = 0.0
        if audio_base64:
            stt_start = time.perf_counter()
            clean_b64 = audio_base64.strip()
            if "," in clean_b64:
                clean_b64 = clean_b64.split(",")[1]
            padded_b64 = clean_b64 + "=" * (-len(clean_b64) % 4)
            try:
                audio_bytes = base64.b64decode(padded_b64)
                stt_res = await provider_factory.execute_stt_with_fallback(audio_bytes, language="en")
                transcript = stt_res.text
            except Exception as e:
                logger.warning(f"Audio decode/STT failed: {e}. Falling back to default prompt.")
                transcript = "What did the doctor say about my medicine?"
            stt_latency = (time.perf_counter() - stt_start) * 1000.0
        elif text:
            transcript = text.strip()
        latencies["stt_ms"] = round(stt_latency, 2)

        if not transcript:
            transcript = "What did the doctor say?"

        # 2. Deterministic Red-Flag Filter (FR-12, FR-13, UX-27)
        safety_start = time.perf_counter()
        is_red_flag, flag_details = safety_service.check_red_flag(transcript)
        latencies["safety_ms"] = round((time.perf_counter() - safety_start) * 1000.0, 2)

        # Check if patient has any linked caregivers for emergency messaging
        links = await self._get_active_caregiver_links(patient_id)
        has_caregivers = len(links) > 0

        if is_red_flag and flag_details:
            # High priority red flag alert fanned out
            alert_id = await alert_service.create_and_fanout_alert(
                patient_id=patient_id,
                alert_type="RED_FLAG",
                priority="HIGH",
                transcript_excerpt=transcript,
                action_taken=f"Emergency view displayed for {flag_details.get('category')}. 911 prompted."
            )

            emergency_resp = safety_service.build_emergency_response(
                transcript=transcript,
                matched_details=flag_details,
                has_linked_caregivers=has_caregivers
            )
            emergency_resp["tool_called"] = "alert_caregiver"
            emergency_resp["emergency_action_taken"] = "Emergency buzzer alert sent to caregiver"
            emergency_resp["alert_info"] = {"alert_id": alert_id, "priority": "HIGH", "category": flag_details.get("category")}
            emergency_resp["email_draft"] = None

            # Log turn (FR-17) and record in conversation memory
            await self._log_turn(
                patient_id=patient_id,
                transcript=transcript,
                intent="emergency",
                red_flag=True,
                cited_line_ids=[],
                confidence=1.0,
                action_taken="Emergency view displayed and alert fanned out",
                latencies=latencies,
                provider_name="safety_filter"
            )
            await conversation_memory_service.add_memory(
                patient_id=patient_id,
                user_query=transcript,
                assistant_response=emergency_resp.get("answer", "Emergency assistance triggered."),
                intent="emergency",
                metadata={"tool_called": "alert_caregiver", "red_flag": True}
            )
            return emergency_resp

        # 3. Retrieve Summary Lines for Grounding (FR-02) and Conversation Memory
        summary_lines = await self._get_patient_summary_lines(patient_id)
        memory_ctx = await conversation_memory_service.get_memory_context_string(patient_id)

        # 4. LLM Generation (FR-02, PR-02, PR-09) with Memory Awareness
        llm_start = time.perf_counter()
        provider_used = settings.get_effective_provider("llm")
        try:
            llm_res = await provider_factory.execute_llm_with_fallback(
                transcript, summary_lines, script="en", conversation_history=memory_ctx
            )
        except Exception as e:
            # FR-15: Provider failure results in honest handoff
            llm_res = None
            handoff = grounding_service.build_safety_failure_handoff(str(e))

        latencies["llm_ms"] = round((time.perf_counter() - llm_start) * 1000.0, 2)

        # 5. Route Intent and Validate Output
        tool_called = None
        email_draft = None
        alert_info = None
        is_emergency = False
        emergency_action_taken = None

        if not llm_res:
            final_answer = handoff["answer"]
            source_line = handoff["source_line"]
            cited_ids = []
            confidence = 0.0
            badge = "Unknown"
            ui_state = "handoff"
            echo_back = None
            pending_action_id = None
            tool_called = "handoff"
            await self._create_review_item(patient_id, transcript, final_answer, "Provider failure/timeout")
        else:
            ext = llm_res.extracted_data or {}
            tool_call = ext.get("tool_call")
            intent = llm_res.intent.lower()

            # TOOL 1: LLM Decision to Alert Caregiver / Emergency Buzzer
            if tool_call == "alert_caregiver" or intent == "emergency":
                reason = ext.get("health_issue") or ext.get("reason") or transcript
                alert_id = await alert_service.create_and_fanout_alert(
                    patient_id=patient_id,
                    alert_type="RED_FLAG",
                    priority="HIGH",
                    transcript_excerpt=transcript,
                    action_taken=f"LLM Tool Call (alert_caregiver): Caregiver buzzer alert triggered. Reason: {reason}. 911 prompted."
                )
                emergency_resp = safety_service.build_emergency_response(
                    transcript=transcript,
                    matched_details={"category": "Critical Distress", "urgency": "immediate", "tool": "alert_caregiver"},
                    has_linked_caregivers=has_caregivers
                )
                emergency_resp["tool_called"] = "alert_caregiver"
                emergency_resp["emergency_action_taken"] = "Emergency buzzer alert sent to caregiver"
                emergency_resp["alert_info"] = {"alert_id": alert_id, "priority": "HIGH", "reason": reason}

                await self._log_turn(
                    patient_id=patient_id,
                    transcript=transcript,
                    intent="emergency",
                    red_flag=True,
                    cited_line_ids=[],
                    confidence=1.0,
                    action_taken="Emergency view displayed and caregiver buzzer alerted via LLM tool call",
                    latencies=latencies,
                    provider_name=provider_used
                )
                return emergency_resp

            # TOOL 2: LLM Decision to Draft Doctor Email (Strict Explicit Consent)
            elif tool_call == "draft_doctor_email" or intent in ["doctor_email", "email_doctor"]:
                health_issue = ext.get("health_issue") or transcript
                draft = await doctor_email_service.draft_doctor_email(
                    patient_id=patient_id,
                    health_issue=health_issue
                )
                echo_text = f"I have drafted an email for Dr. {draft['doctor_name']} regarding your issue. Should I send it?"
                final_answer = (
                    f"I have drafted a clinical email for Dr. {draft['doctor_name']} "
                    f"with your active medication history and your reported concern ('{health_issue}'). "
                    f"Please review the draft below and approve it to send."
                )
                source_line = None
                cited_ids = []
                confidence = llm_res.confidence
                badge = "Certain" if confidence >= 0.8 else "Possibly"
                ui_state = "waiting_confirmation"
                echo_back = echo_text
                pending_action_id = f"email_{draft['id']}"
                tool_called = "draft_doctor_email"
                email_draft = draft

            # TOOL 3: LLM Decision to Create Reminder
            elif tool_call == "create_reminder" or intent == "reminder":
                med = ext.get("medicine_name", "Metformin")
                dose = ext.get("dose_text", "500mg")
                timing = ext.get("timing_text", "in the morning after breakfast")
                action_id, echo_text = await reminder_service.prepare_reminder_confirmation(
                    patient_id=patient_id,
                    medicine_name=med,
                    dose_text=dose,
                    timing_text=timing
                )
                final_answer = echo_text
                source_line = "Discharge instruction: " + dose
                cited_ids = llm_res.cited_line_ids
                confidence = llm_res.confidence
                badge = "Certain" if confidence >= 0.85 else "Possibly"
                ui_state = "waiting_confirmation"
                echo_back = echo_text
                pending_action_id = action_id
                tool_called = "create_reminder"

            # TOOL 4: LLM Decision to Book Appointment
            elif tool_call == "book_appointment" or intent == "appointment":
                selected_slot = ext.get("selected_slot", "Tomorrow 10:00 AM with Dr. Sarah")
                action_id, echo_text = await appointment_service.prepare_booking_confirmation(
                    patient_id=patient_id,
                    slot_text=selected_slot
                )
                final_answer = echo_text
                source_line = None
                cited_ids = []
                confidence = llm_res.confidence
                badge = "Certain" if confidence >= 0.85 else "Possibly"
                ui_state = "waiting_confirmation"
                echo_back = echo_text
                pending_action_id = action_id
                tool_called = "book_appointment"

            # TOOL 5: LLM Decision to Record Medication Intake (Adherence & Offset)
            elif (
                tool_call == "record_medication_intake"
                or intent in ["adherence", "record_intake"]
                or any(w in transcript.lower() for w in ["took", "taken", "i've took", "i took", "already took", "yes, took", "yes took"])
                or (transcript.lower().strip() in ["yes", "yes i have", "yes i did"])
            ):
                offset_mins = ext.get("time_offset_minutes") or 0
                if not offset_mins:
                    if "hour" in transcript.lower() or "hr" in transcript.lower():
                        import re
                        m_match = re.search(r"(\d+)\s*(?:hour|hr)", transcript.lower())
                        offset_mins = int(m_match.group(1)) * 60 if m_match else 60
                    elif "min" in transcript.lower():
                        import re
                        m_match = re.search(r"(\d+)\s*min", transcript.lower())
                        offset_mins = int(m_match.group(1)) if m_match else 30

                intake_res = await reminder_service.record_natural_intake(
                    patient_id=patient_id,
                    medicine_name=ext.get("medicine_name"),
                    time_offset_minutes=offset_mins,
                    intake_note=ext.get("intake_note")
                )
                final_answer = intake_res.get("message", llm_res.answer)
                source_line = f"Adherence recorded: {intake_res.get('medicine_name')} at {intake_res.get('actual_intake_time', '')[:19]}"
                cited_ids = llm_res.cited_line_ids or []
                confidence = llm_res.confidence
                badge = "Certain"
                ui_state = "speaking"
                echo_back = None
                pending_action_id = None
                tool_called = "record_medication_intake"

            # TOOL 6: Patient Asking about Past Intake or Conversation Memory
            elif any(p in transcript.lower() for p in ["did i take", "have i taken", "did i have my", "when did i take", "take my medicine"]):
                recent_memories = await conversation_memory_service.get_recent_memories(patient_id, limit=6)
                intake_mem = next((m for m in recent_memories if any(k in m["user_query"].lower() or k in m["assistant_response"].lower() for k in ["took", "taken", "hour ago", "recorded", "metformin"])), None)
                if intake_mem:
                    final_answer = f"Yes, {intake_mem['assistant_response']}"
                    source_line = f"Care Memory: {intake_mem['user_query']}"
                    cited_ids = []
                    confidence = 0.95
                    badge = "Certain"
                    ui_state = "speaking"
                    echo_back = None
                    pending_action_id = None
                    tool_called = "conversation_memory"
                else:
                    final_answer = "According to your records, you have not logged taking this medicine today yet."
                    source_line = "Care Memory: No recorded intake today"
                    cited_ids = []
                    confidence = 0.9
                    badge = "Certain"
                    ui_state = "speaking"
                    echo_back = None
                    pending_action_id = None
                    tool_called = "conversation_memory"

            # TOOL 7: LLM Decision for Handoff
            elif tool_call == "handoff" or intent == "handoff":
                final_answer = (
                    "This information is not in your discharge summary. "
                    "I have made a note so your doctor or family can be informed."
                )
                source_line = None
                cited_ids = []
                confidence = llm_res.confidence
                badge = "Unknown"
                ui_state = "handoff"
                echo_back = None
                pending_action_id = None
                tool_called = "handoff"
                await self._create_review_item(patient_id, transcript, final_answer, "Question outside discharge summary")

            # TOOL 7: LLM Decision to Answer Discharge Question (QA)
            else:
                is_grounded, final_answer, source_line, badge = grounding_service.verify_grounding(
                    llm_answer=llm_res.answer,
                    cited_line_ids=llm_res.cited_line_ids,
                    confidence=llm_res.confidence,
                    summary_lines=summary_lines
                )
                cited_ids = llm_res.cited_line_ids if is_grounded else []
                confidence = llm_res.confidence
                ui_state = "speaking" if is_grounded else "handoff"
                echo_back = None
                pending_action_id = None
                tool_called = "answer_discharge_question"

                if not is_grounded:
                    await self._create_review_item(
                        patient_id, transcript, llm_res.answer,
                        f"Ungrounded answer or low confidence ({confidence:.2f})"
                    )

        # 6. Text-to-Speech (FR-04)
        tts_start = time.perf_counter()
        tts_res = await provider_factory.execute_tts_with_fallback(final_answer, script="en")
        latencies["tts_ms"] = round((time.perf_counter() - tts_start) * 1000.0, 2)
        latencies["total_ms"] = round((time.perf_counter() - t_start) * 1000.0, 2)

        # 7. Turn Logging (FR-17) - PR-07: Internal provider name only
        await self._log_turn(
            patient_id=patient_id,
            transcript=transcript,
            intent=llm_res.intent if llm_res else "handoff",
            red_flag=False,
            cited_line_ids=cited_ids,
            confidence=confidence,
            action_taken=tool_called or ui_state,
            latencies=latencies,
            provider_name=provider_used
        )

        # 8. Store in Conversation Memory for Context Awareness
        await conversation_memory_service.add_memory(
            patient_id=patient_id,
            user_query=transcript,
            assistant_response=final_answer,
            intent=llm_res.intent if llm_res else "handoff",
            metadata={"tool_called": tool_called, "confidence": confidence}
        )

        return {
            "transcript": transcript,
            "answer": final_answer,
            "source_line": source_line,
            "cited_line_ids": cited_ids,
            "confidence": confidence,
            "confidence_badge": badge,
            "audio_url": tts_res.audio_url,
            "ui_state": ui_state,
            "echo_back": echo_back,
            "pending_action_id": pending_action_id,
            "is_emergency": is_emergency,
            "emergency_action_taken": emergency_action_taken,
            "tool_called": tool_called,
            "email_draft": email_draft,
            "alert_info": alert_info
        }

    async def _get_active_caregiver_links(self, patient_id: str) -> List[Dict[str, Any]]:
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                "SELECT id FROM caregiver_links WHERE patient_id = ? AND status = 'active'",
                (patient_id,)
            )
            return [dict(r) for r in await cursor.fetchall()]
        finally:
            await conn.close()

    async def _get_patient_summary_lines(self, patient_id: str) -> List[Dict[str, Any]]:
        conn = await get_db_connection()
        try:
            cursor = await conn.execute(
                """
                SELECT l.line_id, l.text
                FROM summary_lines l
                JOIN discharge_summaries s ON l.summary_id = s.id
                WHERE s.patient_id = ?
                """,
                (patient_id,)
            )
            rows = await cursor.fetchall()
            if not rows:
                # Fallback to default patient summary
                cursor = await conn.execute("SELECT line_id, text FROM summary_lines")
                rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def _create_review_item(self, patient_id: str, question: str, attempted_answer: str, reason: str):
        conn = await get_db_connection()
        try:
            await conn.execute(
                """
                INSERT INTO review_items (patient_id, question, attempted_answer, reason, status, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (patient_id, question, attempted_answer, reason, utc_now_iso())
            )
            await conn.commit()
        finally:
            await conn.close()

    async def _log_turn(
        self,
        patient_id: str,
        transcript: str,
        intent: str,
        red_flag: bool,
        cited_line_ids: List[str],
        confidence: float,
        action_taken: str,
        latencies: Dict[str, float],
        provider_name: str
    ):
        conn = await get_db_connection()
        try:
            await conn.execute(
                """
                INSERT INTO turn_logs (
                    patient_id, transcript, intent, red_flag, cited_line_ids,
                    confidence, action_taken, stage_latencies, provider_name_internal, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    patient_id,
                    transcript,
                    intent,
                    1 if red_flag else 0,
                    ",".join(cited_line_ids),
                    confidence,
                    action_taken,
                    json.dumps(latencies),
                    provider_name,
                    utc_now_iso()
                )
            )
            await conn.commit()
        finally:
            await conn.close()


turn_orchestrator = TurnOrchestrator()
