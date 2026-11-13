"""Provider adapters for model inference.

All adapters are LiteLLM-backed and provider-independent. The Leader Agent
assigns a specific model/provider to each sub-agent; adapters simply execute
the call using that assignment. Sub-Agents never choose their own model.
"""
from .base import ProviderAdapter, ModelCall, ModelResponse, get_adapter, ADAPTERS, register_adapter
from .litellm_adapter import LiteLLMAdapter, adapter

# Register one LiteLLM-backed adapter per provider. All share the same
# implementation; the provider/model is chosen by the Leader Agent's assignment.
for _provider in [
    "openai",
    "anthropic",
    "google",
    "gemini",
    "llama",
    "mistral",
    "deepseek",
    "qwen",
    "local",
]:
    register_adapter(_provider, adapter)

__all__ = [
    "ProviderAdapter",
    "ModelCall",
    "ModelResponse",
    "get_adapter",
    "ADAPTERS",
    "LiteLLMAdapter",
    "adapter",
]
