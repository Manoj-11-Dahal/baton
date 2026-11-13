"""Comprehensive tests for registry/registry.py — Central Model Registry."""
from orchestration.core.types import (
    ModelCapability,
    ModelRegistryEntry,
    Modality,
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


def test_registry_empty_initially():
    """A fresh registry should have no models until loaded/seeded."""
    reg = ModelRegistry(database_url="postgresql+psycopg2://x:x@localhost:1/x")
    assert reg._cache == {}
    assert reg._cache_loaded_at == 0.0


def test_registry_get_and_list():
    reg = ModelRegistry(database_url="postgresql+psycopg2://x:x@localhost:1/x")
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
    reg._cache_loaded_at = 0

    entry = reg.get(ProviderName.OPENAI, "gpt-4o")
    assert entry is not None
    assert entry.model_id == "gpt-4o"
    assert ModelCapability.CODE_GENERATION in entry.capabilities

    assert reg.get(ProviderName.OPENAI, "nonexistent") is None


def test_registry_capability_and_modality_filter():
    reg = ModelRegistry(database_url="postgresql+psycopg2://x:x@localhost:1/x")
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

    text_models = reg.get_capable_models(ModelCapability.TEXT_GENERATION)
    text_ids = {m.model_id for m in text_models}
    assert "dall-e-3" not in text_ids


def test_registry_never_assumes_modality_support():
    """Anthropic supports image INPUT but not image GENERATION."""
    reg = ModelRegistry(database_url="postgresql+psycopg2://x:x@localhost:1/x")
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


def test_registry_is_capable_and_supports_modality():
    reg = ModelRegistry(database_url="postgresql+psycopg2://x:x@localhost:1/x")
    reg._cache = {
        "openai:gpt-4o": _entry(
            ProviderName.OPENAI, "gpt-4o",
            [ModelCapability.TEXT_GENERATION],
            [Modality.TEXT, Modality.IMAGE],
            enabled=True, availability=True,
        ),
    }
    reg._cache_loaded_at = 0

    assert reg.is_capable(ProviderName.OPENAI, "gpt-4o", ModelCapability.TEXT_GENERATION) is True
    assert reg.is_capable(ProviderName.OPENAI, "gpt-4o", ModelCapability.VIDEO_GENERATION) is False
    assert reg.supports_modality(ProviderName.OPENAI, "gpt-4o", Modality.IMAGE) is True
    assert reg.supports_modality(ProviderName.OPENAI, "gpt-4o", Modality.VIDEO) is False


def test_registry_get_fallbacks():
    reg = ModelRegistry(database_url="postgresql+psycopg2://x:x@localhost:1/x")
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


def test_registry_get_fallbacks_missing():
    """get_fallbacks should skip fallback model ids not in registry."""
    reg = ModelRegistry(database_url="postgresql+psycopg2://x:x@localhost:1/x")
    reg._cache = {
        "openai:gpt-4o": _entry(
            ProviderName.OPENAI, "gpt-4o",
            [ModelCapability.TEXT_GENERATION],
            [Modality.TEXT], enabled=True, availability=True,
            fallback_models=["nonexistent-model"],
        ),
    }
    reg._cache_loaded_at = 0

    entry = reg.get(ProviderName.OPENAI, "gpt-4o")
    fallbacks = reg.get_fallbacks(entry)
    assert fallbacks == []


def test_registry_list_models_filters():
    reg = ModelRegistry(database_url="postgresql+psycopg2://x:x@localhost:1/x")
    reg._cache = {
        "openai:gpt-4o": _entry(
            ProviderName.OPENAI, "gpt-4o",
            [ModelCapability.TEXT_GENERATION],
            [Modality.TEXT], enabled=True, availability=True,
        ),
        "anthropic:claude": _entry(
            ProviderName.ANTHROPIC, "claude",
            [ModelCapability.TEXT_GENERATION],
            [Modality.TEXT], enabled=True, availability=True,
        ),
        "openai:dall-e": _entry(
            ProviderName.OPENAI, "dall-e",
            [ModelCapability.IMAGE_GENERATION],
            [Modality.IMAGE], enabled=True, availability=True,
        ),
    }
    reg._cache_loaded_at = 0

    openai_models = reg.list_models(provider=ProviderName.OPENAI)
    assert len(openai_models) == 2

    text_models = reg.list_models(capability=ModelCapability.TEXT_GENERATION)
    assert len(text_models) == 2

    image_models = reg.list_models(modality=Modality.IMAGE)
    assert len(image_models) == 1
    assert image_models[0].model_id == "dall-e"


def test_seed_defaults_includes_all_providers():
    reg = ModelRegistry(database_url="postgresql+psycopg2://x:x@localhost:1/x")
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

    # DALL-E should not advertise text generation.
    dall_e = [e for e in reg.list_models() if e.model_id == "dall-e-3"][0]
    assert ModelCapability.TEXT_GENERATION not in dall_e.capabilities

    # Local model should exist.
    local = reg.get(ProviderName.LOCAL, "local-llm")
    assert local is not None
