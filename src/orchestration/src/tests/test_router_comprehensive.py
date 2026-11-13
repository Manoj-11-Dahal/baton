"""Additional comprehensive tests for router/router.py — Dynamic Model Router."""
from orchestration.core.types import (
    FallbackReason,
    ModelAssignment,
    ModelCapability,
    ModelRegistryEntry,
    Modality,
    ProviderName,
    TaskRequest,
)
from orchestration.router.router import ModelRouter


def _entry(provider, model_id, capabilities, modalities, latency_ms=1000,
           pricing_output=1.0, context_window=128000, availability=True,
           fallback_models=None):
    return ModelRegistryEntry(
        provider=provider,
        model_id=model_id,
        capabilities=capabilities,
        modalities=modalities,
        latency_ms=latency_ms,
        pricing_output_per_1m=pricing_output,
        context_window=context_window,
        availability=availability,
        fallback_models=fallback_models or [],
    )


def _reg_with_models():
    reg = type("Reg", (), {})()
    entries = {
        "openai:gpt-4o": _entry(
            ProviderName.OPENAI, "gpt-4o",
            [ModelCapability.TEXT_GENERATION, ModelCapability.CODE_GENERATION,
             ModelCapability.REASONING, ModelCapability.MULTIMODAL_INPUT],
            [Modality.TEXT, Modality.IMAGE, Modality.MULTIMODAL],
            latency_ms=1000, pricing_output=10.0, context_window=128000,
            fallback_models=["gpt-4o-mini"],
        ),
        "openai:gpt-4o-mini": _entry(
            ProviderName.OPENAI, "gpt-4o-mini",
            [ModelCapability.TEXT_GENERATION, ModelCapability.CODE_GENERATION],
            [Modality.TEXT, Modality.IMAGE],
            latency_ms=600, pricing_output=0.60, context_window=128000,
        ),
        "anthropic:claude-3-haiku": _entry(
            ProviderName.ANTHROPIC, "claude-3-haiku-20240307",
            [ModelCapability.TEXT_GENERATION, ModelCapability.CODE_GENERATION],
            [Modality.TEXT, Modality.IMAGE, Modality.MULTIMODAL],
            latency_ms=600, pricing_output=1.25, context_window=200000,
        ),
        "gemini:gemini-2.0-flash": _entry(
            ProviderName.GEMINI, "gemini-2.0-flash",
            [ModelCapability.TEXT_GENERATION, ModelCapability.CODE_GENERATION],
            [Modality.TEXT, Modality.IMAGE, Modality.AUDIO, Modality.MULTIMODAL],
            latency_ms=800, pricing_output=0.40, context_window=1000000,
        ),
        "openai:dall-e-3": _entry(
            ProviderName.OPENAI, "dall-e-3",
            [ModelCapability.IMAGE_GENERATION],
            [Modality.IMAGE],
            latency_ms=5000, pricing_output=None, context_window=4000,
        ),
    }
    reg.get = lambda p, m: entries.get(f"{p.value}:{m}")
    reg.get_capable_models = lambda cap, modality=None, provider=None: [
        e for e in entries.values()
        if cap in e.capabilities
        and (provider is None or e.provider == provider)
        and (modality is None or modality in e.modalities)
        and e.enabled and e.availability
    ]
    return reg


def test_route_scores_and_picks_best():
    reg = _reg_with_models()
    router = ModelRouter(registry=reg)
    task = TaskRequest(
        task_type="code",
        modality="text",
        prompt="Write a Python function to add two numbers.",
        required_capabilities=[ModelCapability.CODE_GENERATION],
    )
    decision = router.route(task)
    assert decision.model_id != "unsupported"
    assert decision.provider in (ProviderName.OPENAI, ProviderName.ANTHROPIC, ProviderName.GEMINI)
    assert decision.rationale
    assert len(decision.scored_options) >= 1


def test_route_unsupported_capability_clear_message():
    reg = _reg_with_models()
    router = ModelRouter(registry=reg)
    task = TaskRequest(
        task_type="video",
        modality="video",
        prompt="Generate a video.",
        required_capabilities=[ModelCapability.VIDEO_GENERATION],
    )
    decision = router.route(task)
    assert decision.model_id == "unsupported"
    assert "No available model" in decision.rationale


def test_route_blocked_providers_excluded():
    reg = _reg_with_models()
    router = ModelRouter(registry=reg)
    task = TaskRequest(
        task_type="text",
        modality="text",
        prompt="Hello.",
        required_capabilities=[ModelCapability.TEXT_GENERATION],
        blocked_providers=[ProviderName.OPENAI, ProviderName.ANTHROPIC],
    )
    decision = router.route(task)
    assert decision.provider != ProviderName.OPENAI
    assert decision.provider != ProviderName.ANTHROPIC


def test_route_preferred_provider_bonus():
    reg = _reg_with_models()
    router = ModelRouter(registry=reg)
    task = TaskRequest(
        task_type="text",
        modality="text",
        prompt="Hello.",
        required_capabilities=[ModelCapability.TEXT_GENERATION],
        preferred_provider=ProviderName.ANTHROPIC,
    )
    decision = router.route(task)
    assert decision.provider == ProviderName.ANTHROPIC


def test_route_modality_filter():
    reg = _reg_with_models()
    router = ModelRouter(registry=reg)
    # DALL-E only supports IMAGE modality; requesting TEXT should exclude it.
    task = TaskRequest(
        task_type="image",
        modality="image",
        prompt="Generate an image.",
        required_capabilities=[ModelCapability.IMAGE_GENERATION],
    )
    decision = router.route(task)
    assert decision.model_id == "dall-e-3"
    assert decision.provider == ProviderName.OPENAI


def test_route_to_assignment_creates_active_binding():
    reg = _reg_with_models()
    router = ModelRouter(registry=reg)
    task = TaskRequest(
        task_type="text",
        modality="text",
        prompt="Hello world.",
        required_capabilities=[ModelCapability.TEXT_GENERATION],
    )
    assignment = router.route_to_assignment(task, agent_id="text_agent", assigned_by="leader_agent")
    assert assignment.active is True
    assert assignment.assigned_by == "leader_agent"
    assert assignment.task_id == task.id
    assert assignment.agent_id == "text_agent"


def test_router_is_advisory_only():
    """Router must never assign models to agents."""
    reg = _reg_with_models()
    router = ModelRouter(registry=reg)
    assert not hasattr(router, "assign_model")
    assert not hasattr(router, "reassign_model")


def test_fallback_chain_includes_configured_fallbacks():
    reg = _reg_with_models()
    router = ModelRouter(registry=reg)
    task = TaskRequest(
        task_type="text",
        modality="text",
        prompt="Hello.",
        required_capabilities=[ModelCapability.TEXT_GENERATION],
    )
    decision = router.route(task)
    assert isinstance(decision.fallback_chain, list)
    # gpt-4o has fallback gpt-4o-mini configured
    if decision.model_id == "gpt-4o":
        fb_ids = {f.model_id for f in decision.fallback_chain}
        assert "gpt-4o-mini" in fb_ids


def test_cost_ceiling_excludes_expensive():
    reg = _reg_with_models()
    router = ModelRouter(registry=reg)
    task = TaskRequest(
        task_type="text",
        modality="text",
        prompt="Hello.",
        required_capabilities=[ModelCapability.TEXT_GENERATION],
        max_cost_usd=0.001,
    )
    decision = router.route(task)
    assert decision.model_id == "unsupported" or decision.provider != ProviderName.OPENAI


def test_recommend_fallback_uses_configured_fallbacks():
    reg = _reg_with_models()
    router = ModelRouter(registry=reg)
    task = TaskRequest(
        task_type="text",
        modality="text",
        prompt="Hello.",
        required_capabilities=[ModelCapability.TEXT_GENERATION],
    )
    current = ModelAssignment(
        task_id="t1", agent_id="text_agent",
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        assigned_by="leader_agent", active=True,
        fallback_assignments=[
            ModelAssignment(
                task_id="t1", agent_id="text_agent",
                provider=ProviderName.OPENAI, model_id="gpt-4o-mini",
                assigned_by="leader_agent", active=False,
            )
        ],
    )
    fb = router.recommend_fallback(current, FallbackReason.ERROR, task)
    assert fb is not None
    assert fb.model_id == "gpt-4o-mini"
    assert fb.active is True


def test_recommend_fallback_no_fallback_available():
    reg = _reg_with_models()
    router = ModelRouter(registry=reg)
    task = TaskRequest(
        task_type="video",
        modality="video",
        prompt="Generate video.",
        required_capabilities=[ModelCapability.VIDEO_GENERATION],
    )
    current = ModelAssignment(
        task_id="t1", agent_id="text_agent",
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        assigned_by="leader_agent", active=True,
        fallback_assignments=[],
    )
    fb = router.recommend_fallback(current, FallbackReason.ERROR, task)
    assert fb is None
