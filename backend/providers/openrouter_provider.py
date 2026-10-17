"""OpenRouter Provider Adapter (Free Tier Models).
Offers free access to open-weights models like meta-llama/llama-3.1-8b-instruct:free
via https://openrouter.ai/keys
"""
import time
import json
import httpx
from typing import List, Dict, Any, Optional
from backend.config import settings
from backend.providers.base import (
    LLMProvider, LLMResult,
    ProviderTimeoutError, ProviderRateLimitError, ProviderError
)


class OpenRouterLLMProvider(LLMProvider):
    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.model = settings.OPENROUTER_LLM_MODEL or "meta-llama/llama-3.1-8b-instruct:free"
        self.timeout = settings.PROVIDER_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 8 and "your_" not in self.api_key)

    async def generate_structured(
        self,
        prompt: str,
        summary_lines: List[Dict[str, Any]],
        script: str = "en",
        conversation_history: Optional[str] = None
    ) -> LLMResult:
        if not self.api_key:
            raise ProviderError("OPENROUTER_API_KEY not configured. Please add your key from https://openrouter.ai/keys to .env")

        start = time.perf_counter()
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Sehat Saathi Health Companion"
        }

        numbered_summary = "\n".join([f"[{l['line_id']}] {l['text']}" for l in summary_lines])
        system_prompt = (
            "You are Sehat Saathi, an accessible hospital discharge assistant and medication manager.\n"
            "You must answer strictly using the provided discharge summary lines and memory context.\n"
            "Never give medical advice, never change doses, never invent information.\n"
            "Output valid JSON ONLY in this format:\n"
            "{\n"
            '  "tool_call": "alert_caregiver" | "draft_doctor_email" | "create_reminder" | "book_appointment" | "record_medication_intake" | "answer_discharge_question" | "handoff",\n'
            '  "intent": "qa" | "reminder" | "appointment" | "emergency" | "adherence" | "doctor_email" | "handoff",\n'
            '  "answer": "Clear, simple answer in English.",\n'
            '  "cited_line_ids": ["L1", "L2"],\n'
            '  "confidence": 0.95,\n'
            '  "extracted_data": {\n'
            '    "medicine_name": "name of medicine taken if mentioned, or null",\n'
            '    "time_offset_minutes": 60,\n'
            '    "health_issue": "summary of issue if any"\n'
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
                    raise ProviderRateLimitError("OpenRouter rate limit reached (429)")
                res.raise_for_status()
                data = res.json()
                raw_text = data["choices"][0]["message"]["content"]
                parsed = json.loads(raw_text)

                latency = (time.perf_counter() - start) * 1000.0
                return LLMResult(
                    answer=parsed.get("answer", ""),
                    cited_line_ids=parsed.get("cited_line_ids", []),
                    confidence=float(parsed.get("confidence", 0.95)),
                    intent=parsed.get("intent", "qa"),
                    extracted_data=parsed.get("extracted_data"),
                    latency_ms=latency,
                    raw_response=raw_text
                )
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(f"OpenRouter LLM timed out after {self.timeout}s: {e}")
        except (ProviderRateLimitError, ProviderTimeoutError):
            raise
        except Exception as e:
            raise ProviderError(f"OpenRouter LLM error: {e}")
