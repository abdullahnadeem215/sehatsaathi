"""Groq Cloud Provider Adapters (High-Speed LPU Inference & Whisper STT).
Enforces SRS PR-01, PR-02, PR-05, PR-13.
Offers generous free-tier access via https://console.groq.com/keys
"""
import time
import re
import json
import httpx
from typing import List, Dict, Any, Optional
from backend.config import settings
from backend.providers.base import (
    STTProvider, LLMProvider,
    STTResult, LLMResult,
    ProviderTimeoutError, ProviderRateLimitError, ProviderError
)


class GroqLLMProvider(LLMProvider):
    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_LLM_MODEL or "llama-3.3-70b-versatile"
        self.timeout = settings.PROVIDER_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.startswith("gsk_") and len(self.api_key) > 10)

    async def generate_structured(
        self,
        prompt: str,
        summary_lines: List[Dict[str, Any]],
        script: str = "en",
        conversation_history: Optional[str] = None
    ) -> LLMResult:
        if not self.api_key:
            raise ProviderError("GROQ_API_KEY not configured. Please add your free key from https://console.groq.com/keys to .env")

        start = time.perf_counter()
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        numbered_summary = "\n".join([f"[{l['line_id']}] {l['text']}" for l in summary_lines])
        system_prompt = (
            "You are Sehat Saathi, an intelligent hospital discharge assistant, medication manager, and clinical decision maker.\n"
            "Analyze the patient's statement, previous conversation memory, and select the appropriate tool to call:\n\n"
            "AVAILABLE TOOLS:\n"
            "1. 'alert_caregiver': Call if patient expresses severe acute distress, heart pain, chest pressure, severe breathing difficulty, fainting, or emergency danger. Action: Triggers caregiver buzzer & 911.\n"
            "2. 'draft_doctor_email': Call if patient reports a non-emergency symptom, side effect, discomfort, medication question requiring doctor guidance, or requests to consult/email their doctor. Action: Prepares a concise clinical draft with active medications for patient review & approval.\n"
            "3. 'create_reminder': Call if patient asks to set a reminder or alarm for taking medicine.\n"
            "4. 'book_appointment': Call if patient asks to schedule or book a doctor appointment.\n"
            "5. 'record_medication_intake': Call if patient states or confirms they took their medicine (e.g. 'Yes', 'I took it', 'I took my medicine 1 hour ago', 'I\\'ve took this 1 hour till now', 'Already took it 30 mins ago', 'Yes, taken'). Action: Records the dose adherence and actual intake time.\n"
            "6. 'answer_discharge_question': Call if patient asks a question about their care, previous statements, medicine schedule, or discharge summary. Ground in summary lines and previous conversation memory.\n"
            "7. 'handoff': Call if question cannot be answered from memory or discharge instructions and doesn't require a tool.\n\n"
            "Output valid JSON ONLY in this exact format:\n"
            "{\n"
            '  "tool_call": "alert_caregiver" | "draft_doctor_email" | "create_reminder" | "book_appointment" | "record_medication_intake" | "answer_discharge_question" | "handoff",\n'
            '  "intent": "emergency" | "doctor_email" | "reminder" | "appointment" | "adherence" | "qa" | "handoff",\n'
            '  "answer": "Empathetic, clear, simple answer in English.",\n'
            '  "cited_line_ids": ["L1", "L2"],\n'
            '  "confidence": 0.95,\n'
            '  "extracted_data": {\n'
            '    "health_issue": "summary of the health issue if drafting doctor email or alerting caregiver",\n'
            '    "urgency": "critical" | "high" | "medium",\n'
            '    "medicine_name": "name of medicine taken if mentioned, or null",\n'
            '    "dose_text": "dose text if mentioned, or null",\n'
            '    "timing_text": "...",\n'
            '    "selected_slot": "...",\n'
            '    "action": "taken",\n'
            '    "time_offset_minutes": 60,\n'
            '    "intake_note": "Taken 1 hour ago"\n'
            '  }\n'
            "}"
        )

        history_block = f"\n\n{conversation_history}" if conversation_history else ""
        user_content = f"Discharge Summary:\n{numbered_summary}{history_block}\n\nPatient Query: {prompt}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code == 429:
                    raise ProviderRateLimitError("Groq rate limit reached (429)")
                res.raise_for_status()
                data = res.json()
                raw_text = data["choices"][0]["message"]["content"]
                json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                else:
                    parsed = json.loads(raw_text)

                # Ensure tool_call is recorded in extracted_data
                ext = parsed.get("extracted_data") or {}
                if "tool_call" in parsed and "tool_call" not in ext:
                    ext["tool_call"] = parsed["tool_call"]

                intent = parsed.get("intent", "qa")
                if parsed.get("tool_call") == "alert_caregiver" and intent not in ["emergency"]:
                    intent = "emergency"
                elif parsed.get("tool_call") == "draft_doctor_email" and intent not in ["doctor_email"]:
                    intent = "doctor_email"
                elif parsed.get("tool_call") == "record_medication_intake" and intent not in ["adherence"]:
                    intent = "adherence"

                latency = (time.perf_counter() - start) * 1000.0
                return LLMResult(
                    answer=parsed.get("answer", raw_text.strip()),
                    cited_line_ids=parsed.get("cited_line_ids", []),
                    confidence=float(parsed.get("confidence", 0.95)),
                    intent=intent,
                    extracted_data=ext,
                    latency_ms=latency,
                    raw_response=raw_text
                )
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(f"Groq LLM timed out after {self.timeout}s: {e}")
        except (ProviderRateLimitError, ProviderTimeoutError):
            raise
        except Exception as e:
            raise ProviderError(f"Groq LLM error: {e}")


class GroqSTTProvider(STTProvider):
    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_STT_MODEL or "whisper-large-v3"
        self.timeout = settings.PROVIDER_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.startswith("gsk_") and len(self.api_key) > 10)

    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> STTResult:
        if not self.api_key:
            raise ProviderError("GROQ_API_KEY not configured. Please add your free key to .env")

        start = time.perf_counter()
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        files = {
            "file": ("audio.wav", audio_bytes, "audio/wav")
        }
        data = {
            "model": self.model,
            "language": language
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(url, files=files, data=data, headers=headers)
                if res.status_code == 429:
                    raise ProviderRateLimitError("Groq STT rate limit reached (429)")
                res.raise_for_status()
                result_json = res.json()
                text = result_json.get("text", "")
                latency = (time.perf_counter() - start) * 1000.0
                return STTResult(
                    text=text,
                    language=language,
                    confidence=0.96,
                    latency_ms=latency
                )
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(f"Groq STT timed out after {self.timeout}s: {e}")
        except (ProviderRateLimitError, ProviderTimeoutError):
            raise
        except Exception as e:
            raise ProviderError(f"Groq STT error: {e}")
