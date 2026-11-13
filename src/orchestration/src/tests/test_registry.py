"""Unit tests for the Central Model Registry (in-memory, no Postgres required)."""
import pytest

from orchestration.core.types import (
    Modality,
    ModelCapability,
    ModelRegistryEntry,
    ProviderName,
)
from orchestration.registry.registry import ModelRegistry


def _entry(provider, model_id, capabilities, modalities, **kw):
    return ModelRegistryEntry(
        provider=provider,
        model_id=model_id,
        capabilities=capabilities,
        modalities=modalities,
        **kw,
    )


def test_registry_get_and_list(registry):
    reg = registry
    reg._cache = {
        "openai:gpt-4o": _entry(
            ProviderName.OPENAI, "gpt-4o",
            [ModelCapability.TEXT_GENERATION, ModelCapability.CODE_GENERATION],
            [Modality.TEXT, Modality.IMAGE],
            context_window=128000, enabled=True, availability=True,
        ),
        "anthropic:claude-3-haiku": _entry(
            ProviderName.ANTHROPIC, "claude-3-haiku-20240307",
            [ModelCapability.TEXT_GENERATION],
            [Modality.TEXT],
            context_window=200000, enabled=True, availability=True,
        ),
    }
    reg._cache_loaded_at = 0  # force cache as loaded

    entry = reg.get(ProviderName.OPENAI, "gpt-4o")
    assert entry is not None
    assert entry.model_id == "gpt-4o"
    assert ModelCapability.CODE_GENERATION in entry.capabilities

    assert reg.get(ProviderName.OPENAI, "nonexistent") is None


def test_registry_capability_and_modality_filter(registry):
    reg = registry
    reg._cache = {
        "openai:dall-e-3": _entry(
            ProviderName.OPENAI, "dall-e-3",
            [ModelCapability.IMAGE_GENERATION],
            [Modality.IMAGE], enabled=True, availability=True,
        ),
        "openai:gpt-4o": _entry(
            ProviderName.OPENAI, "gpt-4o",
            [ModelCapability.TEXT_GENERATION, ModelCapability.CODE_GENERATION],
            [Modality.TEXT], enabled=True, availability=True,
        ),
    }
    reg._cache_loaded_at = 0

    image_models = reg.get_capable_models(ModelCapability.IMAGE_GENERATION)
    assert len(image_models) == 1
    assert image_models[0].model_id == "dall-e-3"

    # DALL-E does NOT support text generation — capability deliberately absent.
    text_models = reg.get_capable_models(ModelCapability.TEXT_GENERATION)
    text_ids = {m.model_id for m in text_models}
    assert "dall-e-3" not in text_ids


def test_registry_never_assumes_modality_support(registry):
    reg = registry
    # Anthropic supports image INPUT (multimodal) but not image GENERATION.
    reg._cache = {
        "anthropic:claude-3-5-sonnet": _entry(
            ProviderName.ANTHROPIC, "claude-3-5-sonnet",
            [ModelCapability.TEXT_GENERATION, ModelCapability.MULTIMODAL_INPUT],
            [Modality.TEXT, Modality.IMAGE, Modality.MULTIMODAL],
            enabled=True, availability=True,
        ),
    }
    reg._cache_loaded_at = 0

    gen = reg.get_capable_models(ModelCapability.IMAGE_GENERATION)
    assert gen == [], "Anthropic must not advertise image generation."


def test_registry_fallbacks(registry):
    reg = registry
    reg._cache = {
        "openai:gpt-4o": _entry(
            ProviderName.OPENAI, "gpt-4o",
            [ModelCapability.TEXT_GENERATION],
            [Modality.TEXT], enabled=True, availability=True,
            fallback_models=["gpt-4o-mini"],
        ),
        "openai:gpt-4o-mini": _entry(
            ProviderName.OPENAI, "gpt-4o-mini",
            [ModelCapability.TEXT_GENERATION],
            [Modality.TEXT], enabled=True, availability=True,
        ),
    }
    reg._cache_loaded_at = 0

    entry = reg.get(ProviderName.OPENAI, "gpt-4o")
    fallbacks = reg.get_fallbacks(entry)
    assert len(fallbacks) == 1
    assert fallbacks[0].model_id == "gpt-4o-mini"


def test_seed_defaults_includes_all_providers(registry):
    reg = registry
    reg.seed_defaults()
    providers = {e.provider for e in reg.list_models()}
    expected = {
        ProviderName.OPENAI, ProviderName.ANTHROPIC, ProviderName.GEMINI,
        ProviderName.LLAMA, ProviderName.MISTRAL, ProviderName.DEEPSEEK,
        ProviderName.QWEN, ProviderName.LOCAL,
    }
    assert expected.issubset(providers), f"Missing providers: {expected - providers}"

    # Google should not advertise video generation natively.
    gemini_models = [e for e in reg.list_models() if e.provider == ProviderName.GEMINI]
    for m in gemini_models:
        assert ModelCapability.VIDEO_GENERATION not in m.capabilities, (
            f"{m.model_id} must not advertise native video generation."
        )
