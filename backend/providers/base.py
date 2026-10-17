"""Provider abstraction interfaces and normalized response schemas.
Satisfies SRS PR-01, PR-05, PR-13.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class STTResult(BaseModel):
    text: str
    language: str = "ur"
    confidence: float = 0.95
    latency_ms: float = 0.0


class LLMResult(BaseModel):
    answer: str
    cited_line_ids: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    intent: str = "qa"  # "qa", "reminder", "appointment", "emergency", "handoff"
    extracted_data: Optional[Dict[str, Any]] = None
    latency_ms: float = 0.0
    raw_response: Optional[str] = None


class TTSResult(BaseModel):
    audio_bytes: bytes = b""
    audio_format: str = "wav"
    latency_ms: float = 0.0
    audio_url: Optional[str] = None


class ProviderError(Exception):
    """Base exception for provider failures."""
    pass


class ProviderTimeoutError(ProviderError):
    """Provider exceeded maximum timeout."""
    pass


class ProviderRateLimitError(ProviderError):
    """Provider free-tier or rate limit reached."""
    pass


class STTProvider(ABC):
    def is_configured(self) -> bool:
        """Returns True if provider has valid credentials/endpoints configured."""
        return True

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> STTResult:
        """Convert audio to text and return normalized STTResult."""
        pass


class LLMProvider(ABC):
    def is_configured(self) -> bool:
        """Returns True if provider has valid credentials/endpoints configured."""
        return True

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        summary_lines: List[Dict[str, Any]],
        script: str = "en",
        conversation_history: Optional[str] = None
    ) -> LLMResult:
        """Process turn and return normalized LLMResult with cited line IDs and memory awareness."""
        pass


class TTSProvider(ABC):
    def is_configured(self) -> bool:
        """Returns True if provider has valid credentials/endpoints configured."""
        return True

    @abstractmethod
    async def synthesize(self, text: str, script: str = "en") -> TTSResult:
        """Synthesize text to speech and return normalized TTSResult."""
        pass
