"""Tests for Groq and OpenRouter Provider Integration.
Verifies registration in ProviderFactory, configuration handling, and resilient execution.
"""
import pytest
from backend.config import settings
from backend.providers.factory import ProviderFactory
from backend.providers.groq_provider import GroqLLMProvider, GroqSTTProvider
from backend.providers.openrouter_provider import OpenRouterLLMProvider
from backend.providers.base import ProviderError
from backend.services.turn_orchestrator import turn_orchestrator
from backend.database import init_db_sync


@pytest.fixture(autouse=True)
def setup_db():
    init_db_sync()


def test_provider_factory_groq_and_openrouter_instantiation():
    factory = ProviderFactory()

    # LLM
    groq_llm = factory.get_provider_instance("llm", "groq")
    assert isinstance(groq_llm, GroqLLMProvider)

    openrouter_llm = factory.get_provider_instance("llm", "openrouter")
    assert isinstance(openrouter_llm, OpenRouterLLMProvider)

    # STT
    groq_stt = factory.get_provider_instance("stt", "groq")
    assert isinstance(groq_stt, GroqSTTProvider)


@pytest.mark.asyncio
async def test_groq_fallback_when_unconfigured():
    # When GROQ_API_KEY is not set or empty, provider raises ProviderError
    orig_key = settings.GROQ_API_KEY
    settings.GROQ_API_KEY = None
    try:
        provider = GroqLLMProvider()
        with pytest.raises(ProviderError) as exc_info:
            await provider.generate_structured("test", [])
        assert "GROQ_API_KEY not configured" in str(exc_info.value)
    finally:
        settings.GROQ_API_KEY = orig_key


@pytest.mark.asyncio
async def test_openrouter_fallback_when_unconfigured():
    # When OPENROUTER_API_KEY is not set or empty, provider raises ProviderError
    orig_key = settings.OPENROUTER_API_KEY
    settings.OPENROUTER_API_KEY = None
    try:
        provider = OpenRouterLLMProvider()
        with pytest.raises(ProviderError) as exc_info:
            await provider.generate_structured("test", [])
        assert "OPENROUTER_API_KEY not configured" in str(exc_info.value)
    finally:
        settings.OPENROUTER_API_KEY = orig_key


@pytest.mark.asyncio
async def test_turn_orchestrator_with_groq_provider():
    orig_provider = settings.AI_PROVIDER
    settings.AI_PROVIDER = "groq"
    settings.AUTO_FALLBACK = True
    try:
        res = await turn_orchestrator.process_turn(
            patient_id="default-patient",
            text="When should I take Metformin?",
            script="en"
        )
        assert res is not None
        assert "Metformin" in res["answer"]
    finally:
        settings.AI_PROVIDER = orig_provider


def test_cascade_order_construction():
    factory = ProviderFactory()
    chain_llm = factory.get_cascade_chain("llm")
    assert "mock" in chain_llm
    assert chain_llm[-1] == "mock"  # Mock is always the safety net
    assert "amd" in chain_llm
    assert "groq" in chain_llm
    assert "openrouter" in chain_llm
    assert "huggingface" in chain_llm

    chain_stt = factory.get_cascade_chain("stt")
    assert "groq" in chain_stt
    assert "mock" in chain_stt


def test_circuit_breaker_tripping_and_reset():
    factory = ProviderFactory()
    prov = "huggingface"
    assert factory.is_circuit_open(prov) is False

    factory.trip_circuit(prov, duration=10.0)
    assert factory.is_circuit_open(prov) is True

    factory.reset_circuit(prov)
    assert factory.is_circuit_open(prov) is False


@pytest.mark.asyncio
async def test_cascade_instant_mock_fallback_when_remote_unconfigured():
    import time
    factory = ProviderFactory()
    # Ensure remote providers are skipped via unconfigured or open circuit
    factory.trip_circuit("amd", 60.0)
    factory.trip_circuit("groq", 60.0)
    factory.trip_circuit("openrouter", 60.0)
    factory.trip_circuit("huggingface", 60.0)

    start = time.perf_counter()
    result = await factory.execute_llm_with_fallback(
        prompt="When should I take Metformin?",
        summary_lines=[{"line_id": "L2", "text": "Take Tablet Metformin 500mg once daily in the morning after breakfast."}],
        script="en"
    )
    duration_ms = (time.perf_counter() - start) * 1000.0

    assert result is not None
    assert "Metformin" in result.answer
    # Must complete almost instantaneously (< 100ms)
    assert duration_ms < 100.0

