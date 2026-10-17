"""AMD Developer Cloud Provider Adapters (OpenAI-compatible vLLM & Speech).
Enforces SRS PR-01, PR-02, PR-05, PR-13.
"""
import time
import json
import httpx
from typing import List, Dict, Any, Optional
from backend.config import settings
from backend.providers.base import (
    STTProvider, LLMProvider, TTSProvider,
    STTResult, LLMResult, TTSResult,
    ProviderTimeoutError, ProviderRateLimitError, ProviderError
)


class AMDLLMProvider(LLMProvider):
    def __init__(self):
        self.base_url = settings.AMD_LLM_BASE_URL.rstrip("/") if settings.AMD_LLM_BASE_URL else ""
        self.api_key = settings.AMD_LLM_API_KEY
        self.model = settings.AMD_LLM_MODEL
        self.timeout = settings.PROVIDER_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        return bool(self.base_url and "example.com" not in self.base_url and self.api_key and self.api_key not in ["dummy-key", "mock-amd-key"])

    async def generate_structured(
        self,
        prompt: str,
        summary_lines: List[Dict[str, Any]],
        script: str = "en",
        conversation_history: Optional[str] = None
    ) -> LLMResult:
        start = time.perf_counter()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}" if self.api_key else ""
        }

        # Build context from summary lines
        numbered_summary = "\n".join([f"[{l['line_id']}] {l['text']}" for l in summary_lines])
        system_prompt = (
            "You are Sehat Saathi, an intelligent hospital discharge assistant and clinical decision maker.\n"
            "Analyze the patient's statement and select the appropriate tool to call:\n\n"
            "AVAILABLE TOOLS:\n"
            "1. 'alert_caregiver': Call if patient expresses severe acute distress, heart pain, chest pressure, severe breathing difficulty, fainting, or emergency danger. Action: Triggers caregiver buzzer & 911.\n"
            "2. 'draft_doctor_email': Call if patient reports a non-emergency symptom, side effect, discomfort, medication question requiring doctor guidance, or requests to consult/email their doctor. Action: Prepares a concise clinical draft with active medications for patient review & approval.\n"
            "3. 'create_reminder': Call if patient asks to set a reminder or alarm for taking medicine.\n"
            "4. 'book_appointment': Call if patient asks to schedule or book a doctor appointment.\n"
            "5. 'record_medication_intake': Call if patient states or confirms they took their medicine (e.g. 'Yes', 'I took it', 'I took my medicine 1 hour ago', 'I\\'ve took this 1 hour till now'). Action: Records the dose adherence and actual intake time.\n"
            "6. 'answer_discharge_question': Call if patient asks a factual question about their discharge summary instructions. Ground strictly in provided summary lines.\n"
            "7. 'handoff': Call if question is outside discharge instructions and doesn't require a tool.\n\n"
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
            '    "medicine_name": "...",\n'
            '    "dose_text": "...",\n'
            '    "timing_text": "...",\n'
            '    "selected_slot": "..."\n'
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
                res = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                if res.status_code == 429:
                    raise ProviderRateLimitError("AMD vLLM rate limit reached")
                res.raise_for_status()
                data = res.json()
                raw_text = data["choices"][0]["message"]["content"]
                parsed = json.loads(raw_text)

                ext = parsed.get("extracted_data") or {}
                if "tool_call" in parsed and "tool_call" not in ext:
                    ext["tool_call"] = parsed["tool_call"]

                intent = parsed.get("intent", "qa")
                if parsed.get("tool_call") == "alert_caregiver" and intent not in ["emergency"]:
                    intent = "emergency"
                elif parsed.get("tool_call") == "draft_doctor_email" and intent not in ["doctor_email"]:
                    intent = "doctor_email"

                latency = (time.perf_counter() - start) * 1000.0
                return LLMResult(
                    answer=parsed.get("answer", ""),
                    cited_line_ids=parsed.get("cited_line_ids", []),
                    confidence=float(parsed.get("confidence", 0.9)),
                    intent=intent,
                    extracted_data=ext,
                    latency_ms=latency,
                    raw_response=raw_text
                )
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(f"AMD LLM timed out after {self.timeout}s: {e}")
        except Exception as e:
            raise ProviderError(f"AMD LLM error: {e}")


class AMDSTTProvider(STTProvider):
    def __init__(self):
        self.url = settings.AMD_STT_URL
        self.model = settings.AMD_STT_MODEL
        self.timeout = settings.PROVIDER_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        return bool(self.url and "example.com" not in self.url)

    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> STTResult:
        start = time.perf_counter()
        if not self.url:
            raise ProviderError("AMD STT endpoint URL not configured")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                files = {"file": ("audio.wav", audio_bytes, "audio/wav")}
                data = {"model": self.model, "language": language}
                res = await client.post(self.url, files=files, data=data)
                res.raise_for_status()
                res_data = res.json()
                latency = (time.perf_counter() - start) * 1000.0
                return STTResult(
                    text=res_data.get("text", ""),
                    language=language,
                    confidence=float(res_data.get("confidence", 0.95)),
                    latency_ms=latency
                )
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(f"AMD STT timed out: {e}")
        except Exception as e:
            raise ProviderError(f"AMD STT error: {e}")


class AMDTTSProvider(TTSProvider):
    def __init__(self):
        self.url = settings.AMD_TTS_URL
        self.model = settings.AMD_TTS_MODEL
        self.timeout = settings.PROVIDER_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        return bool(self.url and "example.com" not in self.url)

    async def synthesize(self, text: str, script: str = "en") -> TTSResult:
        start = time.perf_counter()
        if not self.url:
            raise ProviderError("AMD TTS endpoint URL not configured")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(self.url, json={"text": text, "model": self.model})
                res.raise_for_status()
                latency = (time.perf_counter() - start) * 1000.0
                return TTSResult(
                    audio_bytes=res.content,
                    audio_format="wav",
                    latency_ms=latency,
                    audio_url="/static/audio/latest_reply.wav"
                )
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(f"AMD TTS timed out: {e}")
        except Exception as e:
            raise ProviderError(f"AMD TTS error: {e}")
