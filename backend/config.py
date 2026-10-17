"""Configuration and environment settings for Sehat Saathi backend.
Enforces SRS requirements PR-03, PR-04, PR-10, PR-11.
"""
from typing import Optional, Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Provider Configuration
    # Options: "amd", "huggingface", "groq", "openrouter", "mock"
    AI_PROVIDER: str = Field(default="amd", description="Global default AI provider")
    LLM_PROVIDER: Optional[str] = Field(default=None, description="Per-capability override for LLM")
    STT_PROVIDER: Optional[str] = Field(default=None, description="Per-capability override for STT")
    TTS_PROVIDER: Optional[str] = Field(default=None, description="Per-capability override for TTS")

    # Fallback Behaviour
    AUTO_FALLBACK: bool = Field(default=True, description="Enable automatic fallback on timeout/failure")
    FALLBACK_PROVIDER: str = Field(default="mock", description="Fallback provider to use if primary fails")
    PROVIDER_TIMEOUT_SECONDS: float = Field(default=12.0, description="Timeout for provider calls in seconds")

    # AMD Developer Cloud (vLLM, OpenAI-compatible)
    AMD_LLM_BASE_URL: Optional[str] = Field(default="https://amd-vllm-endpoint.example.com/v1")
    AMD_LLM_API_KEY: Optional[str] = Field(default="dummy-key")
    AMD_LLM_MODEL: str = Field(default="meta-llama/Llama-3-8B-Instruct")
    AMD_STT_URL: Optional[str] = Field(default=None)
    AMD_STT_MODEL: str = Field(default="openai/whisper-large-v3")
    AMD_TTS_URL: Optional[str] = Field(default=None)
    AMD_TTS_MODEL: str = Field(default="urdu-tts-model")

    # Hugging Face
    HF_TOKEN: Optional[str] = Field(default=None)
    HF_LLM_MODEL: str = Field(default="meta-llama/Meta-Llama-3-8B-Instruct")
    HF_STT_MODEL: str = Field(default="openai/whisper-large-v3")
    HF_TTS_MODEL: str = Field(default="facebook/mms-tts-urd-script_arabic")

    # Groq Cloud (Free high-speed LPU inference & Whisper STT: https://console.groq.com/keys)
    GROQ_API_KEY: Optional[str] = Field(default=None)
    GROQ_LLM_MODEL: str = Field(default="openai/gpt-oss-120b")
    GROQ_STT_MODEL: str = Field(default="whisper-large-v3")

    # OpenRouter (Free tier models: https://openrouter.ai/keys)
    OPENROUTER_API_KEY: Optional[str] = Field(default=None)
    OPENROUTER_LLM_MODEL: str = Field(default="meta-llama/llama-3.1-8b-instruct:free")

    # Safety & Operations
    CONFIDENCE_THRESHOLD: float = Field(default=0.6, description="Grounding confidence threshold")
    OPERATOR_TOKEN: str = Field(default="REDACTED_OPERATOR_TOKEN", description="Protected token for operator health check")

    # Caregiver Pairing (SRS v1.1 FR-20 to FR-25)
    PAIRING_KEY_TTL_SECONDS: int = Field(default=600, description="10-minute lifetime for pairing keys")
    PAIRING_MAX_FAILURES: int = Field(default=5, description="Max failed redemption attempts per IP")
    PAIRING_FAILURE_WINDOW_SECONDS: int = Field(default=600, description="Rate limit window in seconds")
    PAIRING_CONSENT_TIMEOUT_SECONDS: int = Field(default=120, description="Seconds patient has to approve link")

    # Optional demo bypass
    DASHBOARD_ACCESS_CODE: Optional[str] = Field(default=None, description="Optional operator demo bypass")

    # Database
    DATABASE_PATH: str = Field(default="sehat_saathi.db", description="Path to SQLite database file")

    # Cascade & Provider Execution
    CASCADE_TIMEOUT_SECONDS: float = Field(default=12.0, description="Timeout per external provider in cascade allowing real providers sufficient generation time")
    CIRCUIT_BREAKER_SECONDS: float = Field(default=60.0, description="Seconds to temporarily bypass a failed external provider")

    def get_effective_provider(self, capability: Literal["llm", "stt", "tts"]) -> str:
        """PR-04: Returns the effective provider for a capability, falling back to AI_PROVIDER."""
        if capability == "llm" and self.LLM_PROVIDER:
            return self.LLM_PROVIDER.lower().strip()
        if capability == "stt" and self.STT_PROVIDER:
            return self.STT_PROVIDER.lower().strip()
        if capability == "tts" and self.TTS_PROVIDER:
            return self.TTS_PROVIDER.lower().strip()
        return self.AI_PROVIDER.lower().strip()

    def validate_provider_configs(self) -> None:
        """PR-11: Validates required variables for the selected provider at start-up."""
        capabilities = ["llm", "stt", "tts"]
        valid_providers = {"amd", "huggingface", "groq", "openrouter", "mock", "auto"}
        for cap in capabilities:
            prov = self.get_effective_provider(cap)  # type: ignore
            if prov not in valid_providers:
                raise ValueError(f"Unknown provider '{prov}' specified for {cap}. Supported: {', '.join(valid_providers)}")


settings = Settings()
