"""Protected Operator Health & Diagnostics API.
Enforces SRS Section 7.2, PR-07, PR-12.
"""
from fastapi import APIRouter, Depends
from backend.config import settings
from backend.models.schemas import OperatorHealthResponse, CapabilityHealth
from backend.api.auth import verify_operator_token
from backend.providers.factory import provider_factory

router = APIRouter(prefix="/internal", tags=["Operator Diagnostics"])


@router.get("/health", response_model=OperatorHealthResponse)
def get_operator_health(authorized: bool = Depends(verify_operator_token)):
    """PR-12: Protected operator health endpoint reports active provider and model
    for each capability, last successful call, and recent latency.
    """
    records = provider_factory.health_records

    capabilities = {}
    for cap in ["llm", "stt", "tts"]:
        prov_name = settings.get_effective_provider(cap)  # type: ignore
        model_name = ""
        if prov_name == "amd":
            model_name = settings.AMD_LLM_MODEL if cap == "llm" else (settings.AMD_STT_MODEL if cap == "stt" else settings.AMD_TTS_MODEL)
        elif prov_name == "huggingface":
            model_name = settings.HF_LLM_MODEL if cap == "llm" else (settings.HF_STT_MODEL if cap == "stt" else settings.HF_TTS_MODEL)
        elif prov_name == "groq":
            model_name = settings.GROQ_LLM_MODEL if cap == "llm" else (settings.GROQ_STT_MODEL if cap == "stt" else "mock-tts-v1")
        elif prov_name == "openrouter":
            model_name = settings.OPENROUTER_LLM_MODEL if cap == "llm" else f"mock-{cap}-v1"
        else:
            model_name = f"mock-{cap}-v1"

        rec = records.get(cap, {})
        capabilities[cap] = CapabilityHealth(
            provider=rec.get("provider") or prov_name,
            model=rec.get("model") or model_name,
            last_call=rec.get("last_call"),
            recent_latency_ms=rec.get("recent_latency_ms")
        )

    return OperatorHealthResponse(
        status="healthy",
        global_ai_provider=settings.AI_PROVIDER,
        auto_fallback=settings.AUTO_FALLBACK,
        fallback_provider=settings.FALLBACK_PROVIDER,
        capabilities=capabilities
    )
