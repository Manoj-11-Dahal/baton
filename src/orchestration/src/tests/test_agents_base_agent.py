"""Tests for agents/base_agent.py — SubAgent base class."""
import asyncio

import pytest

from orchestration.adapters.base import ModelCall, ModelResponse, register_adapter
from orchestration.agents.base_agent import SubAgent
from orchestration.core.types import (
    FallbackReason,
    ModelAssignment,
    Modality,
    ProviderName,
    TaskRequest,
    TaskType,
)


class RecordingAdapter:
    """Records calls and returns canned responses."""

    def __init__(self, responses=None, fail_on=None):
        self.responses = responses or {}
        self.fail_on = fail_on or set()
        self.calls = []

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
            content=self.responses.get(call.model_id, "stub response"),
            ok=True,
            usage={"input": 10, "output": 5},
            latency_ms=100,
            cost_usd=0.001,
        )


class ConcreteSubAgent(SubAgent):
    """Concrete sub-agent for testing."""

    def __init__(self, agent_id="test_agent"):
        super().__init__(
            agent_id=agent_id,
            name="Test Sub-Agent",
            description="A test sub-agent.",
            task_type="text",
            system_prompt="You are a test sub-agent.",
        )


def test_sub_agent_init():
    """SubAgent should initialize with no assignment."""
    agent = ConcreteSubAgent()
    assert agent.agent_id == "test_agent"
    assert agent.name == "Test Sub-Agent"
    assert agent.task_type == "text"
    assert agent.assignment is None
    assert agent._call_count == 0


def test_sub_agent_set_assignment_by_leader():
    """set_assignment should accept assignments issued by leader_agent."""
    agent = ConcreteSubAgent()
    a = ModelAssignment(
        task_id="t1", agent_id="test_agent",
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        assigned_by="leader_agent",
    )
    agent.set_assignment(a, issued_by="leader_agent")
    assert agent.assignment is a
    assert agent.assignment.model_id == "gpt-4o"


def test_sub_agent_set_assignment_rejects_non_leader():
    """set_assignment should reject assignments not issued by leader_agent."""
    agent = ConcreteSubAgent()
    a = ModelAssignment(
        task_id="t1", agent_id="test_agent",
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        assigned_by="someone_else",
    )
    with pytest.raises(PermissionError):
        agent.set_assignment(a, issued_by="someone_else")
    assert agent.assignment is None


def test_sub_agent_enforce_model_authority_rejects_switch():
    """_enforce_model_authority should reject model switches."""
    agent = ConcreteSubAgent()
    a = ModelAssignment(
        task_id="t1", agent_id="test_agent",
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        assigned_by="leader_agent",
    )
    agent.set_assignment(a, issued_by="leader_agent")
    with pytest.raises(PermissionError):
        agent._enforce_model_authority(ProviderName.ANTHROPIC, "claude-3-haiku")
    # Assignment unchanged
    assert agent.assignment.model_id == "gpt-4o"
    assert agent.assignment.provider == ProviderName.OPENAI


def test_sub_agent_enforce_model_authority_allows_same():
    """_enforce_model_authority should allow the assigned model."""
    agent = ConcreteSubAgent()
    a = ModelAssignment(
        task_id="t1", agent_id="test_agent",
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        assigned_by="leader_agent",
    )
    agent.set_assignment(a, issued_by="leader_agent")
    agent._enforce_model_authority(ProviderName.OPENAI, "gpt-4o")


def test_sub_agent_require_assignment_no_assignment():
    """_require_assignment should raise RuntimeError when no assignment."""
    agent = ConcreteSubAgent()
    with pytest.raises(RuntimeError):
        agent._require_assignment()


@pytest.mark.asyncio
async def test_sub_agent_execute_uses_assigned_model(monkeypatch):
    """execute() should call the adapter with the leader-assigned model."""
    agent = ConcreteSubAgent()
    a = ModelAssignment(
        task_id="t1", agent_id="test_agent",
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        assigned_by="leader_agent",
    )
    agent.set_assignment(a, issued_by="leader_agent")

    rec = RecordingAdapter(responses={"gpt-4o": "openai result"})
    register_adapter("openai", rec)

    try:
        import orchestration.agents.base_agent as base_mod
        orig_get = base_mod.get_adapter

        def fake_get(name):
            if name == "openai":
                return rec
            return orig_get(name)

        monkeypatch.setattr(base_mod, "get_adapter", fake_get)

        task = TaskRequest(
            task_type=TaskType.TEXT,
            modality=Modality.TEXT,
            prompt="Say hello.",
        )
        result = await agent.execute(task)

        assert result.ok is True
        assert result.content == "openai result"
        assert result.model_id == "gpt-4o"
        assert result.provider == ProviderName.OPENAI
        assert result.assignment_id == a.id
        assert agent._call_count == 1
        # The adapter was called with the assigned model
        assert len(rec.calls) == 1
        assert rec.calls[0].model_id == "gpt-4o"
    finally:
        from orchestration.adapters.base import _ADAPTERS
        _ADAPTERS.pop("openai", None)


@pytest.mark.asyncio
async def test_sub_agent_execute_no_assignment_raises():
    """execute() should raise RuntimeError when no model assigned."""
    agent = ConcreteSubAgent()
    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Hello.",
    )
    with pytest.raises(RuntimeError):
        asyncio.run(agent.execute(task))


@pytest.mark.asyncio
async def test_sub_agent_execute_provider_error():
    """execute() should return an AgentResult with ok=False on provider error."""
    agent = ConcreteSubAgent()
    a = ModelAssignment(
        task_id="t1", agent_id="test_agent",
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        assigned_by="leader_agent",
    )
    agent.set_assignment(a, issued_by="leader_agent")

    rec = RecordingAdapter(responses={}, fail_on={"gpt-4o"})
    register_adapter("openai", rec)

    try:
        import orchestration.agents.base_agent as base_mod
        orig_get = base_mod.get_adapter

        def fake_get(name):
            if name == "openai":
                return rec
            return orig_get(name)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(base_mod, "get_adapter", fake_get)

        task = TaskRequest(
            task_type=TaskType.TEXT,
            modality=Modality.TEXT,
            prompt="Hello.",
        )
        result = await agent.execute(task)

        assert result.ok is False
        assert result.error == "simulated error"
        assert result.content == ""
    finally:
        from orchestration.adapters.base import _ADAPTERS
        _ADAPTERS.pop("openai", None)
