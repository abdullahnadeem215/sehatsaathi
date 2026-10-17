"""Hugging Face Provider Adapters (Inference API with cold-start & rate-limit handling).
Enforces SRS PR-01, PR-02, PR-05, PR-13.
"""
import os
import re
import time
import json
import asyncio
import httpx
from typing import List, Dict, Any, Optional
from backend.config import settings
from backend.providers.base import (
    STTProvider, LLMProvider, TTSProvider,
    STTResult, LLMResult, TTSResult,
    ProviderTimeoutError, ProviderRateLimitError, ProviderError
)


class HFLLMProvider(LLMProvider):
    def __init__(self):
        self.token = settings.HF_TOKEN
        self.model = settings.HF_LLM_MODEL
        self.timeout = settings.PROVIDER_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        return bool(self.token and len(str(self.token).strip()) > 10 and not str(self.token).strip().startswith("dummy"))

    async def generate_structured(
        self,
        prompt: str,
        summary_lines: List[Dict[str, Any]],
        script: str = "en",
        conversation_history: Optional[str] = None
    ) -> LLMResult:
        start = time.perf_counter()
        url = f"https://router.huggingface.co/hf-inference/models/{self.model}"
        headers = {
            "Authorization": f"Bearer {self.token}" if self.token else "",
            "Content-Type": "application/json"
        }

        numbered_summary = "\n".join([f"[{l['line_id']}] {l['text']}" for l in summary_lines])
        history_block = f"\n\n{conversation_history}" if conversation_history else ""
        formatted_prompt = (
            f"<|system|>\nYou are Sehat Saathi, an accessible English discharge assistant. "
            f"Ground all answers only in this discharge summary and memory:\n{numbered_summary}{history_block}\n"
            f"Output strictly valid JSON with keys: intent, answer, cited_line_ids, confidence.<|end|>\n"
            f"<|user|>\n{prompt}<|end|>\n<|assistant|>\n"
        )

        payload = {
            "inputs": formatted_prompt,
            "parameters": {
                "max_new_tokens": 150,
                "temperature": 0.1,
                "return_full_text": False
            }
        }

        # PR-13: Handle cold start 503 with bounded retries
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    res = await client.post(url, json=payload, headers=headers)
                    if res.status_code == 503:
                        # Model loading
                        error_json = res.json()
                        wait_sec = min(float(error_json.get("estimated_time", 2.0)), 4.0)
                        if attempt < max_retries:
                            await asyncio.sleep(wait_sec)
                            continue
                        raise ProviderError("Hugging Face model cold-start timed out")
                    if res.status_code == 402:
                        raise ProviderRateLimitError("Hugging Face account credits exhausted (402 Payment Required)")
                    if res.status_code == 429:
                        raise ProviderRateLimitError("Hugging Face rate limit reached (429)")
                    res.raise_for_status()

                    output = res.json()
                    raw_text = output[0]["generated_text"] if isinstance(output, list) else str(output)

                    # Extract JSON substring if surrounded by markdown or formatting
                    json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
                    if json_match:
                        raw_json = json_match.group(0)
                        data = json.loads(raw_json)
                    else:
                        data = {"answer": raw_text.strip(), "cited_line_ids": [], "confidence": 0.5, "intent": "qa"}

                    latency = (time.perf_counter() - start) * 1000.0
                    return LLMResult(
                        answer=data.get("answer", ""),
                        cited_line_ids=data.get("cited_line_ids", []),
                        confidence=float(data.get("confidence", 0.8)),
                        intent=data.get("intent", "qa"),
                        latency_ms=latency,
                        raw_response=raw_text
                    )
            except httpx.TimeoutException as e:
                raise ProviderTimeoutError(f"HF LLM timed out: {e}")
            except (ProviderRateLimitError, ProviderTimeoutError):
                raise
            except Exception as e:
                if attempt == max_retries:
                    raise ProviderError(f"HF LLM failed: {e}")


class HFSTTProvider(STTProvider):
    def __init__(self):
        self.token = settings.HF_TOKEN
        self.model = settings.HF_STT_MODEL
        self.timeout = settings.PROVIDER_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        return bool(self.token and len(str(self.token).strip()) > 10 and not str(self.token).strip().startswith("dummy"))

    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> STTResult:
        start = time.perf_counter()
        url = f"https://router.huggingface.co/hf-inference/models/{self.model}"
        headers = {
            "Authorization": f"Bearer {self.token}" if self.token else "",
            "Content-Type": "audio/wav"
        }

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    res = await client.post(url, content=audio_bytes, headers=headers)
                    if res.status_code == 503:
                        # PR-13: Handle cold-start loading
                        err_data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                        wait_sec = min(float(err_data.get("estimated_time", 2.0)), 4.0)
                        if attempt < max_retries:
                            await asyncio.sleep(wait_sec)
                            continue
                        raise ProviderError("Hugging Face STT cold-start timed out")
                    if res.status_code == 402:
                        raise ProviderRateLimitError("Hugging Face account credits exhausted (402 Payment Required)")
                    if res.status_code == 429:
                        raise ProviderRateLimitError("HF STT rate limit reached (429)")
                    res.raise_for_status()
                    data = res.json()
                    text = data.get("text", "")
                    latency = (time.perf_counter() - start) * 1000.0
                    return STTResult(
                        text=text,
                        language=language,
                        confidence=0.92,
                        latency_ms=latency
                    )
            except httpx.TimeoutException as e:
                raise ProviderTimeoutError(f"HF STT timed out: {e}")
            except (ProviderRateLimitError, ProviderTimeoutError):
                raise
            except Exception as e:
                if attempt == max_retries:
                    raise ProviderError(f"HF STT error: {e}")


class HFTTSProvider(TTSProvider):
    def __init__(self):
        self.token = settings.HF_TOKEN
        self.model = settings.HF_TTS_MODEL
        self.timeout = settings.PROVIDER_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        return bool(self.token and len(str(self.token).strip()) > 10 and not str(self.token).strip().startswith("dummy"))

    async def synthesize(self, text: str, script: str = "en") -> TTSResult:
        start = time.perf_counter()
        url = f"https://router.huggingface.co/hf-inference/models/{self.model}"
        headers = {
            "Authorization": f"Bearer {self.token}" if self.token else "",
            "Content-Type": "application/json"
        }

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    res = await client.post(url, json={"inputs": text}, headers=headers)
                    if res.status_code == 503:
                        # PR-13: Handle cold-start loading
                        err_data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                        wait_sec = min(float(err_data.get("estimated_time", 2.0)), 4.0)
                        if attempt < max_retries:
                            await asyncio.sleep(wait_sec)
                            continue
                        raise ProviderError("Hugging Face TTS cold-start timed out")
                    if res.status_code == 402:
                        raise ProviderRateLimitError("Hugging Face account credits exhausted (402 Payment Required)")
                    if res.status_code == 429:
                        raise ProviderRateLimitError("HF TTS rate limit reached (429)")
                    res.raise_for_status()

                    # Save synthesized audio to static directory for client playback
                    audio_bytes = res.content
                    out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "audio", "hf_reply.wav")
                    try:
                        os.makedirs(os.path.dirname(out_path), exist_ok=True)
                        with open(out_path, "wb") as f:
                            f.write(audio_bytes)
                    except Exception:
                        pass

                    latency = (time.perf_counter() - start) * 1000.0
                    return TTSResult(
                        audio_bytes=audio_bytes,
                        audio_format="wav",
                        latency_ms=latency,
                        audio_url="/static/audio/hf_reply.wav"
                    )
            except httpx.TimeoutException as e:
                raise ProviderTimeoutError(f"HF TTS timed out: {e}")
            except (ProviderRateLimitError, ProviderTimeoutError):
                raise
            except Exception as e:
                if attempt == max_retries:
                    raise ProviderError(f"HF TTS error: {e}")
