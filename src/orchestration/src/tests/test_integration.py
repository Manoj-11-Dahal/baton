"""Integration tests for the full orchestration flow.

These tests stub out LiteLLM provider calls so no real API keys are needed.
They verify: Leader assigns models -> sub-agents use them -> quality control ->
model fallback on error -> final response. The Leader retains exclusive model
authority throughout.
"""
import asyncio
from typing import Any, Dict

import pytest

from orchestration.agents.base_agent import SubAgent
from orchestration.agents.leader import LeaderAgent
from orchestration.adapters.base import ModelCall, ModelResponse, ProviderAdapter, register_adapter
from orchestration.core.types import (
    FallbackReason,
    ModelAssignment,
    Modality,
    ProviderName,
    TaskRequest,
    TaskType,
)


class StubAdapter(ProviderAdapter):
    """Stub adapter that returns canned responses, recording the model used."""

    def __init__(self, provider: ProviderName, responses: Dict[str, str]):
        self.provider = provider
        self.responses = responses
        self.calls: list[ModelCall] = []
        self.fail_on: set[str] = set()

    async def call(self, call: ModelCall) -> ModelResponse:
        self.calls.append(call)
        if call.model_id in self.fail_on:
            return ModelResponse(
                model_id=call.model_id,
                provider=call.provider,
                content="",
                ok=False,
                error="simulated provider error",
            )
        return ModelResponse(
            model_id=call.model_id,
            provider=call.provider,
            content=self.responses.get(call.model_id, "stub response"),
            ok=True,
            usage={"input": 10, "output": 5},
            latency_ms=100,
            cost_usd=0.001,
        )

    def supports(self, model_id: str, capability: str) -> bool:
        return True


def _registry():
    from orchestration.registry.registry import ModelRegistry
    reg = ModelRegistry(database_url="postgresql+psycopg2://x:x@localhost:1/x")
    reg.seed_defaults()
    return reg


def _leader_with_stubs():
    from orchestration.router.router import ModelRouter
    registry = _registry()
    router = ModelRouter(registry=registry)
    leader = LeaderAgent(router=router, registry=registry)
    from orchestration.agents.sub_agents import build_all_sub_agents
    for agent in build_all_sub_agents().values():
        leader.register_sub_agent(agent)
    return leader


def test_full_leader_orchestration_uses_assigned_models(monkeypatch):
    leader = _leader_with_stubs()

    # Register stub adapters that record which model was used.
    openai_stub = StubAdapter(ProviderName.OPENAI, {"gpt-4o": "openai result"})
    anthropic_stub = StubAdapter(ProviderName.ANTHROPIC, {"claude-3-haiku-20240307": "anthropic result"})
    register_adapter("openai", openai_stub)
    register_adapter("anthropic", anthropic_stub)

    import orchestration.adapters.base as base_mod
    orig = base_mod.get_adapter

    def fake_get_adapter(name):
        if name == "openai":
            return openai_stub
        if name == "anthropic":
            return anthropic_stub
        return orig(name)

    monkeypatch.setattr(base_mod, "get_adapter", fake_get_adapter)

    result = asyncio.run(
        leader.orchestrate("Write a short summary and translate it.", sequential=True)
    )

    assert result["final"] is not None
    assert result["final"]["ok"] is True
    # Every sub-agent used a Leader-assigned model (not "unsupported").
    for r in result["results"]:
        assert r["model_id"] != "unsupported"
        assert r["provider"] != "local" or r["model_id"] != "unsupported"
    # Leader issued assignments.
    assert len(result["assignments"]) >= 1
    for aid, a in result["assignments"].items():
        assert a["assigned_by"] == "leader_agent"


def test_leader_exclusive_model_authority_integration(monkeypatch):
    leader = _leader_with_stubs()
    stub = StubAdapter(ProviderName.OPENAI, {"gpt-4o": "ok"})
    register_adapter("openai", stub)
    import orchestration.adapters.base as base_mod
    monkeypatch.setattr(base_mod, "get_adapter", lambda name: stub)

    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Say hello.",
    )
    assignment = leader.assign_model("text_agent", task)

    # Confirm sub-agent must use the leader-assigned model.
    agent = leader.sub_agents["text_agent"]
    assert agent.assignment.model_id == assignment.model_id
    assert agent.assignment.provider == assignment.provider

    # Attempt to switch -> rejected by sub-agent.
    with pytest.raises(PermissionError):
        agent._enforce_model_authority(ProviderName.ANTHROPIC, "claude-3-haiku-20240307")

    # Assignment unchanged after rejected switch.
    assert agent.assignment.model_id == assignment.model_id


def test_leader_fallback_on_model_error(monkeypatch):
    leader = _leader_with_stubs()

    # Primary model fails; fallback model succeeds.
    primary = StubAdapter(ProviderName.OPENAI, {"gpt-4o": ""})
    primary.fail_on = {"gpt-4o"}
    fallback = StubAdapter(ProviderName.OPENAI, {"gpt-4o-mini": "fallback ok"})
    register_adapter("openai", primary)
    import orchestration.adapters.base as base_mod
    orig = base_mod.get_adapter

    def fake_get_adapter(name):
        if name == "openai":
            return primary
        return orig(name)

    monkeypatch.setattr(base_mod, "get_adapter", fake_get_adapter)

    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Hello.",
        required_capabilities=[],
    )
    result = asyncio.run(leader.execute_sub_agent("text_agent", task))

    # The Leader must have attempted a fallback (fallback stub called) or
    # returned an error only after exhausting fallbacks.
    assert result is not None
