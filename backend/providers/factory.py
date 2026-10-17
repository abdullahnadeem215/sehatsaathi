"""Provider Factory and Resilient Execution Engine with Low-Latency Cascade.
Enforces SRS PR-01, PR-03, PR-04, PR-08, PR-09, PR-12.

Features:
- Instant multi-tier provider cascade (AMD -> Groq -> OpenRouter -> HuggingFace -> Mock).
- 0.00ms bypass for unconfigured providers (no wasted HTTP connections or timeouts).
- Circuit breaker: suspends failing providers for 60s (or 300s for exhausted credits).
- Adaptive timeout bounds (settings.CASCADE_TIMEOUT_SECONDS).
- Guaranteed local fallback to Mock if all remote services are down/exhausted.
"""
import time
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from backend.config import settings
from backend.providers.base import (
    STTProvider, LLMProvider, TTSProvider,
    STTResult, LLMResult, TTSResult, ProviderError
)
from backend.providers.amd_provider import AMDLLMProvider, AMDSTTProvider, AMDTTSProvider
from backend.providers.huggingface_provider import HFLLMProvider, HFSTTProvider, HFTTSProvider
from backend.providers.groq_provider import GroqLLMProvider, GroqSTTProvider
from backend.providers.openrouter_provider import OpenRouterLLMProvider
from backend.providers.mock_provider import MockLLMProvider, MockSTTProvider, MockTTSProvider
from backend.utils import utc_now_iso

logger = logging.getLogger("sehat_saathi.providers")


class ProviderFactory:
    def __init__(self):
        # Health tracking for PR-12
        self.health_records: Dict[str, Dict[str, Any]] = {
            "llm": {"provider": "", "model": "", "last_call": None, "recent_latency_ms": None},
            "stt": {"provider": "", "model": "", "last_call": None, "recent_latency_ms": None},
            "tts": {"provider": "", "model": "", "last_call": None, "recent_latency_ms": None},
        }
        # Circuit breaker dictionary: provider_name -> unix timestamp when circuit cools down
        self._circuit_breakers: Dict[str, float] = {}

    def is_circuit_open(self, provider_name: str) -> bool:
        """Returns True if the provider is currently in cooldown due to recent failures."""
        p_name = provider_name.lower().strip()
        expiry = self._circuit_breakers.get(p_name, 0.0)
        return time.time() < expiry

    def trip_circuit(self, provider_name: str, duration: Optional[float] = None) -> None:
        """Trips the circuit breaker for a provider, temporarily bypassing it."""
        p_name = provider_name.lower().strip()
        cooldown = duration if duration is not None else settings.CIRCUIT_BREAKER_SECONDS
        self._circuit_breakers[p_name] = time.time() + cooldown
        logger.warning(f"Circuit breaker tripped for {p_name.upper()} (cooldown: {cooldown:.1f}s)")

    def reset_circuit(self, provider_name: str) -> None:
        """Resets the circuit breaker when a provider successfully responds."""
        self._circuit_breakers.pop(provider_name.lower().strip(), None)

    def get_cascade_chain(self, capability: str) -> List[str]:
        """Returns the ordered list of providers to attempt for a capability.
        The configured primary is prioritized, followed by the remaining fast cascade.
        """
        primary = settings.get_effective_provider(capability).lower().strip()
        if capability == "llm":
            base_chain = ["amd", "groq", "openrouter", "huggingface", "mock"]
        elif capability == "stt":
            base_chain = ["amd", "groq", "huggingface", "mock"]
        elif capability == "tts":
            base_chain = ["amd", "huggingface", "mock"]
        else:
            base_chain = ["mock"]

        if primary == "mock":
            return ["mock"]

        chain: List[str] = []
        if primary in base_chain:
            chain.append(primary)
        for p in base_chain:
            if p not in chain:
                chain.append(p)
        return chain

    def get_provider_instance(self, capability: str, provider_name: str):
        provider_name = provider_name.lower().strip()
        if capability == "llm":
            if provider_name == "amd":
                return AMDLLMProvider()
            elif provider_name == "huggingface":
                return HFLLMProvider()
            elif provider_name == "groq":
                return GroqLLMProvider()
            elif provider_name == "openrouter":
                return OpenRouterLLMProvider()
            else:
                return MockLLMProvider()
        elif capability == "stt":
            if provider_name == "amd":
                return AMDSTTProvider()
            elif provider_name == "huggingface":
                return HFSTTProvider()
            elif provider_name == "groq":
                return GroqSTTProvider()
            else:
                return MockSTTProvider()
        elif capability == "tts":
            if provider_name == "amd":
                return AMDTTSProvider()
            elif provider_name == "huggingface":
                return HFTTSProvider()
            else:
                return MockTTSProvider()
        raise ValueError(f"Unknown capability {capability}")

    def get_primary_provider(self, capability: str):
        provider_name = settings.get_effective_provider(capability)
        return self.get_provider_instance(capability, provider_name), provider_name

    def get_fallback_provider(self, capability: str):
        fallback_name = settings.FALLBACK_PROVIDER.lower().strip()
        return self.get_provider_instance(capability, fallback_name), fallback_name

    def _get_model_name(self, capability: str, provider_name: str) -> str:
        provider_name = provider_name.lower().strip()
        if capability == "llm":
            if provider_name == "amd":
                return settings.AMD_LLM_MODEL
            elif provider_name == "huggingface":
                return settings.HF_LLM_MODEL
            elif provider_name == "groq":
                return settings.GROQ_LLM_MODEL
            elif provider_name == "openrouter":
                return settings.OPENROUTER_LLM_MODEL
            return "mock-llama3"
        elif capability == "stt":
            if provider_name == "amd":
                return settings.AMD_STT_MODEL
            elif provider_name == "huggingface":
                return settings.HF_STT_MODEL
            elif provider_name == "groq":
                return settings.GROQ_STT_MODEL
            return "mock-whisper"
        elif capability == "tts":
            if provider_name == "amd":
                return settings.AMD_TTS_MODEL
            elif provider_name == "huggingface":
                return settings.HF_TTS_MODEL
            return "mock-tts"
        return "unknown"

    async def execute_llm_with_fallback(
        self,
        prompt: str,
        summary_lines: list,
        script: str = "en",
        conversation_history: Optional[str] = None
    ) -> LLMResult:
        """Executes LLM call with low-latency cascade, circuit breaker, and memory awareness."""
        cascade = self.get_cascade_chain("llm")
        primary_name = cascade[0] if cascade else "mock"
        last_exc: Optional[Exception] = None

        for i, prov_name in enumerate(cascade):
            # 1. Circuit breaker check (0.00ms)
            if prov_name != "mock" and self.is_circuit_open(prov_name):
                logger.debug(f"Circuit breaker active for {prov_name.upper()} LLM. Skipping in 0.00ms.")
                continue

            # 2. Configuration pre-flight (0.00ms)
            try:
                inst = self.get_provider_instance("llm", prov_name)
            except Exception as e:
                logger.debug(f"Instantiating {prov_name} LLM failed: {e}")
                continue

            if not inst.is_configured():
                logger.debug(f"Provider {prov_name.upper()} is not configured. Skipping in 0.00ms.")
                continue

            model_name = self._get_model_name("llm", prov_name)
            logger.info(f"Invoking {prov_name.upper()} LLM (Model: {model_name}) with prompt: '{prompt[:60]}...'")

            try:
                if prov_name == "mock":
                    result = await inst.generate_structured(prompt, summary_lines, script, conversation_history)
                else:
                    timeout_sec = min(settings.CASCADE_TIMEOUT_SECONDS, settings.PROVIDER_TIMEOUT_SECONDS)
                    result = await asyncio.wait_for(
                        inst.generate_structured(prompt, summary_lines, script, conversation_history),
                        timeout=timeout_sec
                    )

                logger.info(f"{prov_name.upper()} LLM succeeded in {result.latency_ms:.1f}ms")
                self.reset_circuit(prov_name)
                health_label = prov_name if prov_name == primary_name else f"{primary_name}->{prov_name} (cascade)"
                self._record_health("llm", health_label, model_name, result.latency_ms)
                return result

            except Exception as exc:
                last_exc = exc
                logger.warning(f"Provider {prov_name.upper()} LLM failed: {exc}")
                if prov_name != "mock":
                    err_str = str(exc)
                    cooldown = 300.0 if ("402" in err_str or "401" in err_str or "credits exhausted" in err_str.lower()) else settings.CIRCUIT_BREAKER_SECONDS
                    self.trip_circuit(prov_name, duration=cooldown)

                if not settings.AUTO_FALLBACK:
                    raise

                logger.info("PR-09: Cascading to next available provider...")
                continue

        if last_exc:
            raise last_exc
        raise ProviderError("All LLM providers in cascade exhausted")

    async def execute_stt_with_fallback(self, audio_bytes: bytes, language: str = "en") -> STTResult:
        """Executes STT call with low-latency cascade and circuit breaker."""
        cascade = self.get_cascade_chain("stt")
        primary_name = cascade[0] if cascade else "mock"
        last_exc: Optional[Exception] = None

        for i, prov_name in enumerate(cascade):
            if prov_name != "mock" and self.is_circuit_open(prov_name):
                logger.debug(f"Circuit breaker active for {prov_name.upper()} STT. Skipping in 0.00ms.")
                continue

            try:
                inst = self.get_provider_instance("stt", prov_name)
            except Exception:
                continue

            if not inst.is_configured():
                logger.debug(f"Provider {prov_name.upper()} STT is not configured. Skipping in 0.00ms.")
                continue

            model_name = self._get_model_name("stt", prov_name)
            logger.info(f"Invoking {prov_name.upper()} STT (Model: {model_name})...")

            try:
                if prov_name == "mock":
                    result = await inst.transcribe(audio_bytes, language)
                else:
                    timeout_sec = min(settings.CASCADE_TIMEOUT_SECONDS, settings.PROVIDER_TIMEOUT_SECONDS)
                    result = await asyncio.wait_for(
                        inst.transcribe(audio_bytes, language),
                        timeout=timeout_sec
                    )

                logger.info(f"{prov_name.upper()} STT succeeded in {result.latency_ms:.1f}ms")
                self.reset_circuit(prov_name)
                health_label = prov_name if prov_name == primary_name else f"{primary_name}->{prov_name} (cascade)"
                self._record_health("stt", health_label, model_name, result.latency_ms)
                return result

            except Exception as exc:
                last_exc = exc
                logger.warning(f"Provider {prov_name.upper()} STT failed: {exc}")
                if prov_name != "mock":
                    self.trip_circuit(prov_name)

                if not settings.AUTO_FALLBACK:
                    raise

                logger.info("PR-09: Cascading to next available STT provider...")
                continue

        if last_exc:
            raise last_exc
        raise ProviderError("All STT providers in cascade exhausted")

    async def execute_tts_with_fallback(self, text: str, script: str = "en") -> TTSResult:
        """Executes TTS call with low-latency cascade and circuit breaker."""
        cascade = self.get_cascade_chain("tts")
        primary_name = cascade[0] if cascade else "mock"
        last_exc: Optional[Exception] = None

        for i, prov_name in enumerate(cascade):
            if prov_name != "mock" and self.is_circuit_open(prov_name):
                continue

            try:
                inst = self.get_provider_instance("tts", prov_name)
            except Exception:
                continue

            if not inst.is_configured():
                continue

            model_name = self._get_model_name("tts", prov_name)

            try:
                if prov_name == "mock":
                    result = await inst.synthesize(text, script)
                else:
                    timeout_sec = min(settings.CASCADE_TIMEOUT_SECONDS, settings.PROVIDER_TIMEOUT_SECONDS)
                    result = await asyncio.wait_for(
                        inst.synthesize(text, script),
                        timeout=timeout_sec
                    )

                self.reset_circuit(prov_name)
                health_label = prov_name if prov_name == primary_name else f"{primary_name}->{prov_name} (cascade)"
                self._record_health("tts", health_label, model_name, result.latency_ms)
                return result

            except Exception as exc:
                last_exc = exc
                logger.warning(f"Provider {prov_name.upper()} TTS failed: {exc}")
                if prov_name != "mock":
                    self.trip_circuit(prov_name)

                if not settings.AUTO_FALLBACK:
                    raise

                continue

        if last_exc:
            raise last_exc
        raise ProviderError("All TTS providers in cascade exhausted")

    def _record_health(self, capability: str, provider: str, model: str, latency_ms: float):
        self.health_records[capability] = {
            "provider": provider,
            "model": model,
            "last_call": utc_now_iso(),
            "recent_latency_ms": round(latency_ms, 2)
        }


provider_factory = ProviderFactory()
