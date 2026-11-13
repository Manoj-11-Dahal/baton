"""Unit tests for the Dynamic Model Router (advisory only)."""
from orchestration.core.types import (
    Modality,
    ModelCapability,
    ModelRegistryEntry,
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


def test_route_returns_recommendation(router):
    task = TaskRequest(
        task_type="code",
        modality="text",
        prompt="Write a Python function to add two numbers.",
        required_capabilities=[ModelCapability.CODE_GENERATION],
    )
    decision = router.route(task)
    assert decision.model_id != "unsupported"
    assert decision.rationale
    assert isinstance(decision.fallback_chain, list)


def test_route_unsupported_capability_reported(router):
    # No model in the registry supports video generation.
    task = TaskRequest(
        task_type="video",
        modality="video",
        prompt="Generate a 10-second video of a cat.",
        required_capabilities=[ModelCapability.VIDEO_GENERATION],
    )
    decision = router.route(task)
    assert decision.model_id == "unsupported"
    assert "No available model" in decision.rationale


def test_route_respects_blocked_providers(router):
    task = TaskRequest(
        task_type="text",
        modality="text",
        prompt="Write a short poem.",
        required_capabilities=[ModelCapability.TEXT_GENERATION],
        blocked_providers=[ProviderName.OPENAI],
    )
    decision = router.route(task)
    assert decision.model_id != "unsupported"
    assert decision.provider != ProviderName.OPENAI


def test_route_prefers_preferred_provider(router):
    task = TaskRequest(
        task_type="text",
        modality="text",
        prompt="Say hello.",
        required_capabilities=[ModelCapability.TEXT_GENERATION],
        preferred_provider=ProviderName.ANTHROPIC,
    )
    decision = router.route(task)
    assert decision.provider == ProviderName.ANTHROPIC


def test_route_to_assignment(router):
    task = TaskRequest(
        task_type="text",
        modality="text",
        prompt="Hello world.",
        required_capabilities=[ModelCapability.TEXT_GENERATION],
    )
    assignment = router.route_to_assignment(task, agent_id="text_agent", assigned_by="leader_agent")
    assert assignment.active is True
    assert assignment.assigned_by == "leader_agent"
    assert assignment.provider != ProviderName.LOCAL or assignment.model_id != "unsupported"


def test_router_is_advisory_only(router):
    """The router has no method to assign models to agents — only the Leader can."""
    assert not hasattr(router, "assign_model")
    assert not hasattr(router, "reassign_model")


def test_fallback_chain_built(router):
    task = TaskRequest(
        task_type="text",
        modality="text",
        prompt="Hello.",
        required_capabilities=[ModelCapability.TEXT_GENERATION],
    )
    decision = router.route(task)
    # Should have at least one fallback when available.
    assert isinstance(decision.scored_options, list)
    assert len(decision.scored_options) >= 1


def test_cost_ceiling_filter(router):
    task = TaskRequest(
        task_type="text",
        modality="text",
        prompt="Hello.",
        required_capabilities=[ModelCapability.TEXT_GENERATION],
        max_cost_usd=0.001,  # extremely low, should exclude expensive models
    )
    decision = router.route(task)
    # Either unsupported (all too expensive) or a cheap model.
    assert decision.model_id == "unsupported" or decision.provider != ProviderName.OPENAI
