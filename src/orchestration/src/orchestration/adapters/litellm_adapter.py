"""LiteLLM-backed provider adapter.

Supports OpenAI, Anthropic, Google Gemini, Meta Llama, Mistral, DeepSeek,
Qwen, and local OpenAI-compatible models through a single LiteLLM interface.
The adapter never selects a model — it invokes exactly the model_id and
provider given in the ModelCall (assigned by the Leader Agent).
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import litellm
from litellm import completion

from ..core.observability import get_observability
from ..core.types import ProviderName
from .base import ModelCall, ModelResponse, ProviderAdapter

# Surface cost/latency info from LiteLLM responses.
litellm.set_verbose = False


class LiteLLMAdapter(ProviderAdapter):
    """Unified adapter over LiteLLM for all supported providers."""

    # Map our ProviderName to LiteLLM model-name prefixes where needed.
    PROVIDER_PREFIX = {
        ProviderName.OPENAI: "",
        ProviderName.ANTHROPIC: "anthropic/",
        ProviderName.GOOGLE: "gemini/",
        ProviderName.GEMINI: "gemini/",
        ProviderName.LLAMA: "",
        ProviderName.MISTRAL: "mistral/",
        ProviderName.DEEPSEEK: "",
        ProviderName.QWEN: "",
        ProviderName.LOCAL: "",
    }

    # Env var for each provider's API key.
    API_KEY_ENV = {
        ProviderName.OPENAI: "OPENAI_API_KEY",
        ProviderName.ANTHROPIC: "ANTHROPIC_API_KEY",
        ProviderName.GOOGLE: "GOOGLE_API_KEY",
        ProviderName.GEMINI: "GEMINI_API_KEY",
        ProviderName.LLAMA: "LLAMA_API_KEY",
        ProviderName.MISTRAL: "MISTRAL_API_KEY",
        ProviderName.DEEPSEEK: "DEEPSEEK_API_KEY",
        ProviderName.QWEN: "QWEN_API_KEY",
        ProviderName.LOCAL: "LOCAL_LLM_API_KEY",
    }

    def __init__(self):
        self.obs = get_observability()

    def _model_name(self, provider: ProviderName, model_id: str) -> str:
        prefix = self.PROVIDER_PREFIX.get(provider, "")
        # If model_id already carries a provider prefix, use as-is.
        if "/" in model_id or model_id.startswith(prefix):
            return model_id
        return f"{prefix}{model_id}"

    def _api_key(self, provider: ProviderName, call: ModelCall) -> Optional[str]:
        if call.api_key:
            return call.api_key
        env = self.API_KEY_ENV.get(provider)
        if env:
            return os.environ.get(env)
        return None

    def _extra_headers(self, provider: ProviderName, base_url: Optional[str]) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if base_url:
            headers["X-Base-Url"] = base_url
        return headers

    async def call(self, call: ModelCall) -> ModelResponse:
        start = time.time()
        obs = self.obs
        model_name = self._model_name(call.provider, call.model_id)
        api_key = self._api_key(call.provider, call)

        # Build LiteLLM call kwargs.
        kwargs: Dict[str, Any] = {
            "model": model_name,
            "messages": call.messages,
            "timeout": call.timeout_sec,
        }
        if call.temperature is not None:
            kwargs["temperature"] = call.temperature
        if call.max_output_tokens is not None:
            kwargs["max_tokens"] = call.max_output_tokens
        if call.tools:
            kwargs["tools"] = call.tools
        if call.response_format:
            kwargs["response_format"] = call.response_format
        if call.base_url:
            kwargs["api_base"] = call.base_url
        if api_key:
            kwargs["api_key"] = api_key

        try:
            with obs.span(
                "provider.call",
                attributes={
                    "provider": call.provider.value,
                    "model_id": call.model_id,
                    "call_id": call.id,
                },
            ):
                # LiteLLM's completion is sync; run in thread to avoid blocking.
                import asyncio

                response = await asyncio.to_thread(lambda: completion(**kwargs))
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.time() - start) * 1000)
            return ModelResponse(
                model_id=call.model_id,
                provider=call.provider,
                content="",
                latency_ms=latency_ms,
                ok=False,
                error=str(exc),
            )

        latency_ms = int((time.time() - start) * 1000)
        content = ""
        try:
            content = response.choices[0].message.content or ""
        except Exception:  # noqa: BLE001
            content = str(response)

        # Usage & cost from LiteLLM.
        usage: Dict[str, Any] = {}
        cost_usd = 0.0
        try:
            usage = dict(response.usage or {}) if hasattr(response, "usage") else {}
        except Exception:
            usage = {}
        try:
            cost_usd = float(getattr(response, "_hidden_params", {}).get("response_cost", 0.0) or 0.0)
        except Exception:
            cost_usd = 0.0

        return ModelResponse(
            model_id=call.model_id,
            provider=call.provider,
            content=content,
            usage=usage,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            ok=True,
            raw=response,
        )

    def supports(self, model_id: str, capability: str) -> bool:
        return True

    def estimate_cost(self, model_id: str, prompt_tokens: int, output_tokens: int) -> float:
        # LiteLLM can compute completion cost; fall back to 0 if unknown.
        try:
            return float(litellm.completion_cost(model=model_id, prompt_tokens=prompt_tokens, completion_tokens=output_tokens) or 0.0)
        except Exception:
            return 0.0


# Singleton instance.
adapter = LiteLLMAdapter()
