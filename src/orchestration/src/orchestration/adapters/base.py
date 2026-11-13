"""Base adapter interface and registry."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..core.types import ProviderName


class ModelCall:
    """A single model invocation requested by an agent (via the Leader)."""
    def __init__(
        self,
        model_id: str,
        provider: ProviderName,
        messages: List[Dict[str, Any]],
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        timeout_sec: int = 120,
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.id = uuid4().hex
        self.model_id = model_id
        self.provider = provider
        self.messages = messages
        self.base_url = base_url
        self.api_key = api_key
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.timeout_sec = timeout_sec
        self.tools = tools or []
        self.response_format = response_format
        self.metadata = metadata or {}


class ModelResponse:
    """Structured response from a provider adapter."""
    def __init__(
        self,
        *,
        model_id: str,
        provider: ProviderName,
        content: str,
        usage: Optional[Dict[str, Any]] = None,
        latency_ms: int = 0,
        cost_usd: float = 0.0,
        ok: bool = True,
        error: Optional[str] = None,
        structured: Optional[Dict[str, Any]] = None,
        raw: Optional[Any] = None,
    ):
        self.model_id = model_id
        self.provider = provider
        self.content = content
        self.usage = usage or {}
        self.latency_ms = latency_ms
        self.cost_usd = cost_usd
        self.ok = ok
        self.error = error
        self.structured = structured
        self.raw = raw


class ProviderAdapter:
    """Interface all provider adapters implement."""

    async def call(self, call: ModelCall) -> ModelResponse:
        raise NotImplementedError

    def supports(self, model_id: str, capability: str) -> bool:
        """Whether this adapter believes the model supports a capability."""
        return True

    def estimate_cost(self, model_id: str, prompt_tokens: int, output_tokens: int) -> float:
        return 0.0


_ADAPTERS: Dict[str, ProviderAdapter] = {}


def register_adapter(name: str, adapter: ProviderAdapter) -> None:
    _ADAPTERS[name] = adapter


def get_adapter(name: str) -> ProviderAdapter:
    if name not in _ADAPTERS:
        raise KeyError(f"No adapter registered for provider '{name}'.")
    return _ADAPTERS[name]


def ADAPTERS() -> Dict[str, ProviderAdapter]:
    return dict(_ADAPTERS)
