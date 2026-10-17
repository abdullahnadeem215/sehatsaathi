"""Deterministic high-performance mock provider (English-only Edition).
Enables offline testing, CI/CD verification, and local development.
Also serves as fallback provider when external networks/endpoints are unavailable.
"""
import time
import re
from typing import List, Dict, Any, Optional
from backend.providers.base import (
    STTProvider, LLMProvider, TTSProvider,
    STTResult, LLMResult, TTSResult
)


class MockSTTProvider(STTProvider):
    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> STTResult:
        start = time.perf_counter()
        text = "What did the doctor say about taking my morning tablet?"
        latency = (time.perf_counter() - start) * 1000.0
        return STTResult(
            text=text,
            language=language,
            confidence=0.98,
            latency_ms=latency
        )


class MockLLMProvider(LLMProvider):
    async def generate_structured(
        self,
        prompt: str,
        summary_lines: List[Dict[str, Any]],
        script: str = "en",
        conversation_history: Optional[str] = None
    ) -> LLMResult:
        start = time.perf_counter()
        prompt_lower = prompt.lower()

        # 0a. Tool Decision: Emergency / Caregiver Alert
        if any(w in prompt_lower for w in ["heart", "chest pain", "severe pain", "breathless", "faint", "bleeding", "stroke", "numbness"]):
            latency = (time.perf_counter() - start) * 1000.0
            return LLMResult(
                answer="Emergency assistance required. I am triggering an emergency buzzer to your family caregiver and prompting 911.",
                cited_line_ids=[],
                confidence=1.0,
                intent="emergency",
                extracted_data={
                    "tool_call": "alert_caregiver",
                    "urgency": "critical",
                    "health_issue": prompt
                },
                latency_ms=latency
            )

        # 0b. Tool Decision: Draft Doctor Email
        if any(w in prompt_lower for w in ["email", "doctor", "consult", "message", "dr.", "rash", "stomach", "dizzy", "headache", "side effect", "advice"]):
            latency = (time.perf_counter() - start) * 1000.0
            return LLMResult(
                answer="I have drafted a concise clinical email for your doctor with your current concern and prescription history. Please review and approve it to send.",
                cited_line_ids=[],
                confidence=0.95,
                intent="doctor_email",
                extracted_data={
                    "tool_call": "draft_doctor_email",
                    "health_issue": prompt
                },
                latency_ms=latency
            )

        # 0c. Tool Decision: Record Medication Intake / Adherence
        if any(w in prompt_lower for w in ["took", "taken", "i've took", "i took", "already took", "yes, took", "yes i took", "yes took"]) or (prompt_lower.strip() in ["yes", "yes i have", "yes i did"] and "reminder" not in prompt_lower):
            offset_mins = 0
            if "hour" in prompt_lower or "hr" in prompt_lower:
                m_match = re.search(r"(\d+)\s*(?:hour|hr)", prompt_lower)
                offset_mins = int(m_match.group(1)) * 60 if m_match else 60
            elif "min" in prompt_lower:
                m_match = re.search(r"(\d+)\s*min", prompt_lower)
                offset_mins = int(m_match.group(1)) if m_match else 30

            med = "Metformin"
            if "atorvastatin" in prompt_lower:
                med = "Atorvastatin"
            elif "amlodipine" in prompt_lower:
                med = "Amlodipine"
            elif "aspirin" in prompt_lower:
                med = "Aspirin"

            time_desc = f"about {offset_mins // 60} hour ago" if offset_mins >= 60 else (f"{offset_mins} minutes ago" if offset_mins > 0 else "just now")
            latency = (time.perf_counter() - start) * 1000.0
            return LLMResult(
                answer=f"I've recorded that you took your {med} {time_desc}. Great job staying on track with your routine!",
                cited_line_ids=["L2"],
                confidence=0.98,
                intent="adherence",
                extracted_data={
                    "tool_call": "record_medication_intake",
                    "medicine_name": med,
                    "action": "taken",
                    "time_offset_minutes": offset_mins,
                    "intake_note": f"Taken {time_desc}"
                },
                latency_ms=latency
            )

        # 0d. Memory Awareness & Recall: Prior conversations or past intake
        if any(w in prompt_lower for w in ["did i take", "when did i take", "what did i take", "what did we talk about", "remember", "previous"]):
            latency = (time.perf_counter() - start) * 1000.0
            if conversation_history and ("metformin" in conversation_history.lower() or "taken" in conversation_history.lower()):
                return LLMResult(
                    answer="Yes, according to your conversation records and adherence logs, you took your Metformin 500 mg about an hour ago. You are all up to date!",
                    cited_line_ids=["L2"],
                    confidence=0.98,
                    intent="qa",
                    extracted_data={"memory_recalled": True},
                    latency_ms=latency
                )
            return LLMResult(
                answer="According to your records, you are scheduled for Metformin 500 mg in the morning and Amlodipine 5 mg at night.",
                cited_line_ids=["L2", "L3"],
                confidence=0.95,
                intent="qa",
                extracted_data={"memory_recalled": True},
                latency_ms=latency
            )
        if any(w in prompt_lower for w in ["reminder", "remind", "alarm"]):
            med = "Metformin"
            dose = "500mg"
            timing = "in the morning after breakfast"
            cited = ["L2"]

            if any(k in prompt_lower for k in ["amlodipine", "night", "dinner", "blood pressure"]):
                med = "Amlodipine"
                dose = "5mg"
                timing = "at night after dinner"
                cited = ["L3"]

            latency = (time.perf_counter() - start) * 1000.0
            return LLMResult(
                answer=f"I heard: {med} {dose} {timing}. Is that correct?",
                cited_line_ids=cited,
                confidence=0.95,
                intent="reminder",
                extracted_data={
                    "tool_call": "create_reminder",
                    "medicine_name": med,
                    "dose_text": dose,
                    "timing_text": timing
                },
                latency_ms=latency
            )

        # 2. Check for appointment intent (FR-10)
        if any(w in prompt_lower for w in ["appointment", "booking", "slot", "schedule an appointment", "book", "consultation slot"]):
            slot = "Tomorrow 10:00 AM with Dr. Sarah"
            if "afternoon" in prompt_lower or "2:00" in prompt_lower:
                slot = "Tomorrow 2:00 PM with Dr. Sarah"

            latency = (time.perf_counter() - start) * 1000.0
            return LLMResult(
                answer=f"I heard: Book appointment for {slot}. Is that correct?",
                cited_line_ids=[],
                confidence=0.95,
                intent="appointment",
                extracted_data={
                    "selected_slot": slot
                },
                latency_ms=latency
            )

        # 3. Check for out-of-scope / medical diagnosis / advice questions (FR-05)
        out_of_scope_cues = [
            "mango", "ice cream", "double my dose", "double", "cancer", "liver",
            "target blood pressure", "number for my age", "stop taking"
        ]
        if any(c in prompt_lower for c in out_of_scope_cues):
            latency = (time.perf_counter() - start) * 1000.0
            return LLMResult(
                answer="This information is not in your discharge summary. I have made a note so your doctor or family can be informed.",
                cited_line_ids=[],
                confidence=0.2,
                intent="handoff",
                latency_ms=latency
            )

        # 4. Check against summary lines
        matched_line = None
        for line in summary_lines:
            lid = line["line_id"]
            txt = line.get("text", "").lower()

            # Dynamic check: match if words from the summary line appear in the prompt (e.g. dynamic prescriptions like Aspirin)
            keywords = [w for w in re.findall(r"\b[a-zA-Z]{4,}\b", txt) if w not in ["take", "with", "after", "daily", "once", "tablet", "glass", "water", "patient"]]
            if any(kw in prompt_lower for kw in keywords):
                matched_line = line
                break

            if lid == "L2" and any(k in prompt_lower for k in ["morning", "breakfast", "metformin"]):
                matched_line = line
                break
            elif lid == "L3" and any(k in prompt_lower for k in ["night", "dinner", "amlodipine"]):
                matched_line = line
                break
            elif lid == "L4" and any(k in prompt_lower for k in ["panadol", "fever", "body ache", "pain"]):
                matched_line = line
                break
            elif lid == "L5" and any(k in prompt_lower for k in ["weight", "lift", "heavy", "5 kg", "grocery"]):
                matched_line = line
                break
            elif lid == "L6" and any(k in prompt_lower for k in ["salt", "diet", "oily", "food", "restrictions"]):
                matched_line = line
                break
            elif lid == "L7" and any(k in prompt_lower for k in ["walk", "walking", "evening", "recommendations"]):
                matched_line = line
                break
            elif lid == "L8" and any(k in prompt_lower for k in ["follow-up", "follow up", "room 14", "26 october", "consultation", "scheduled"]):
                matched_line = line
                break
            elif lid == "L1" and any(k in prompt_lower for k in ["admitted", "hospital", "diabetes management", "hypertension", "why was i"]):
                matched_line = line
                break

        latency = (time.perf_counter() - start) * 1000.0

        if matched_line:
            return LLMResult(
                answer=matched_line.get("text", ""),
                cited_line_ids=[matched_line["line_id"]],
                confidence=0.95,
                intent="qa",
                latency_ms=latency
            )

        # 5. Default fallback to honest handoff (UX-28)
        return LLMResult(
            answer="This information is not in your discharge summary. I have made a note so your doctor or family can be informed.",
            cited_line_ids=[],
            confidence=0.2,
            intent="handoff",
            latency_ms=latency
        )


class MockTTSProvider(TTSProvider):
    # Standard 44-byte valid RIFF WAV header for silence
    SILENT_WAV_HEADER = (
        b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
        b"\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    )

    async def synthesize(self, text: str, script: str = "en") -> TTSResult:
        start = time.perf_counter()
        latency = (time.perf_counter() - start) * 1000.0
        return TTSResult(
            audio_bytes=self.SILENT_WAV_HEADER,
            audio_format="wav",
            latency_ms=latency,
            audio_url="/static/audio/sample_reply.wav"
        )
