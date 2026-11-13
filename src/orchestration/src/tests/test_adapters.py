"""Tests for adapters/base.py and adapters/litellm_adapter.py."""
from typing import Any, Dict, List

import pytest

from orchestration.adapters.base import (
    ModelCall,
    ModelResponse,
    ProviderAdapter,
    get_adapter,
    register_adapter,
)
from orchestration.adapters.litellm_adapter import LiteLLMAdapter, adapter
from orchestration.core.types import ProviderName


class RecordingAdapter(ProviderAdapter):
    """Test adapter that records calls and returns canned responses."""

    def __init__(self, responses: Dict[str, str] = None, fail_on: set = None):
        self.responses = responses or {}
        self.fail_on = fail_on or set()
        self.calls: List[ModelCall] = []

    async def call(self, call: ModelCall) -> ModelResponse:
        self.calls.append(call)
        if call.model_id in self.fail_on:
            return ModelResponse(
                model_id=call.model_id,
                provider=call.provider,
                content="",
                ok=False,
                error="simulated error",
            )
        return ModelResponse(
            model_id=call.model_id,
            provider=call.provider,
            content=self.responses.get(call.model_id, "default response"),
            ok=True,
            usage={"input": 10, "output": 5},
            latency_ms=100,
            cost_usd=0.001,
        )


def test_model_call_creation():
    """ModelCall should store all provided fields."""
    call = ModelCall(
        model_id="gpt-4o",
        provider=ProviderName.OPENAI,
        messages=[{"role": "user", "content": "hello"}],
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        temperature=0.7,
        max_output_tokens=1000,
        timeout_sec=60,
        tools=[{"name": "tool1", "description": "d", "parameters": {}}],
        response_format={"type": "json_object"},
        metadata={"key": "val"},
    )
    assert call.model_id == "gpt-4o"
    assert call.provider == ProviderName.OPENAI
    assert call.messages == [{"role": "user", "content": "hello"}]
    assert call.base_url == "https://api.openai.com/v1"
    assert call.api_key == "sk-test"
    assert call.temperature == 0.7
    assert call.max_output_tokens == 1000
    assert call.timeout_sec == 60
    assert len(call.tools) == 1
    assert call.response_format == {"type": "json_object"}
    assert call.metadata == {"key": "val"}
    assert isinstance(call.id, str)


def test_model_response_creation():
    """ModelResponse should store all fields."""
    r = ModelResponse(
        model_id="gpt-4o",
        provider=ProviderName.OPENAI,
        content="hello",
        usage={"input": 10, "output": 5},
        latency_ms=150,
        cost_usd=0.002,
        ok=True,
        structured={"foo": "bar"},
    )
    assert r.model_id == "gpt-4o"
    assert r.provider == ProviderName.OPENAI
    assert r.content == "hello"
    assert r.usage == {"input": 10, "output": 5}
    assert r.latency_ms == 150
    assert r.cost_usd == 0.002
    assert r.ok is True
    assert r.structured == {"foo": "bar"}
    assert r.raw is None


def test_provider_adapter_interface_raises():
    """ProviderAdapter.call should raise NotImplementedError."""
    adapter = ProviderAdapter()
    with pytest.raises(NotImplementedError):
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            adapter.call(ModelCall(model_id="x", provider=ProviderName.OPENAI, messages=[]))
        )


def test_register_and_get_adapter():
    """register_adapter / get_adapter should register and retrieve adapters."""
    rec = RecordingAdapter(responses={"gpt-4o": "hi"})
    register_adapter("test-provider", rec)
    retrieved = get_adapter("test-provider")
    assert retrieved is rec
    # Cleanup
    from orchestration.adapters.base import _ADAPTERS
    _ADAPTERS.pop("test-provider", None)


def test_get_adapter_unknown_raises():
    """get_adapter should raise KeyError for unknown provider."""
    from orchestration.adapters.base import _ADAPTERS
    # Ensure it's not registered
    _ADAPTERS.pop("nonexistent-provider", None)
    with pytest.raises(KeyError):
        get_adapter("nonexistent-provider")


def test_adapters_dict_returns_copy():
    """ADAPTERS() should return a copy of the registry."""
    from orchestration.adapters.base import ADAPTERS, _ADAPTERS
    original_len = len(_ADAPTERS)
    result = ADAPTERS()
    assert isinstance(result, dict)
    assert len(result) == original_len


def test_litellm_adapter_model_name_openai():
    """OpenAI model names should not get a prefix."""
    a = LiteLLMAdapter()
    assert a._model_name(ProviderName.OPENAI, "gpt-4o") == "gpt-4o"


def test_litellm_adapter_model_name_anthropic():
    """Anthropic model names should get the 'anthropic/' prefix."""
    a = LiteLLMAdapter()
    assert a._model_name(ProviderName.ANTHROPIC, "claude-3-haiku-20240307") == "anthropic/claude-3-haiku-20240307"


def test_litellm_adapter_model_name_gemini():
    """Gemini model names should get the 'gemini/' prefix."""
    a = LiteLLMAdapter()
    assert a._model_name(ProviderName.GEMINI, "gemini-2.0-flash") == "gemini/gemini-2.0-flash"


def test_litellm_adapter_model_name_already_prefixed():
    """Model IDs already carrying a prefix should be used as-is."""
    a = LiteLLMAdapter()
    assert a._model_name(ProviderName.OPENAI, "openai/gpt-4o") == "openai/gpt-4o"


def test_litellm_adapter_api_key_from_call():
    """api_key from ModelCall should take precedence."""
    a = LiteLLMAdapter()
    call = ModelCall(
        model_id="gpt-4o", provider=ProviderName.OPENAI,
        messages=[], api_key="call-key",
    )
    assert a._api_key(ProviderName.OPENAI, call) == "call-key"


def test_litellm_adapter_api_key_from_env(monkeypatch):
    """api_key should fall back to environment variable."""
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    a = LiteLLMAdapter()
    call = ModelCall(model_id="gpt-4o", provider=ProviderName.OPENAI, messages=[])
    assert a._api_key(ProviderName.OPENAI, call) == "env-key"


def test_litellm_adapter_api_key_none_when_missing(monkeypatch):
    """api_key should be None when not in call or env."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    a = LiteLLMAdapter()
    call = ModelCall(model_id="gpt-4o", provider=ProviderName.OPENAI, messages=[])
    assert a._api_key(ProviderName.OPENAI, call) is None


def test_litellm_adapter_singleton_is_registered():
    """The module-level adapter instance should be registered for all providers."""
    from orchestration.adapters import ADAPTERS
    adapters = ADAPTERS()
    for provider in ["openai", "anthropic", "google", "gemini", "llama", "mistral", "deepseek", "qwen", "local"]:
        assert provider in adapters
        assert adapters[provider] is adapter


def test_litellm_adapter_estimate_cost():
    """estimate_cost should delegate to litellm.completion_cost."""
    a = LiteLLMAdapter()
    # Should not raise even without pricing data
    cost = a.estimate_cost("gpt-4o", 100, 50)
    assert isinstance(cost, float)
