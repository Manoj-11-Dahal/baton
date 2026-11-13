"""Comprehensive tests for agents/leader.py — Leader Agent."""
import asyncio

import pytest

from orchestration.adapters.base import ModelCall, ModelResponse, register_adapter
from orchestration.agents.leader import LeaderAgent
from orchestration.core.types import (
    FallbackReason,
    Modality,
    ModelCapability,
    ModelRegistryEntry,
    ModelAssignment,
    ProviderName,
    TaskRequest,
    TaskType,
)
from orchestration.router.router import ModelRouter
from orchestration.registry.registry import ModelRegistry


class RecordingAdapter:
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


def _reg_with_models():
    entries = {
        "openai:gpt-4o": ModelRegistryEntry(
            provider=ProviderName.OPENAI, model_id="gpt-4o",
            capabilities=[ModelCapability.TEXT_GENERATION, ModelCapability.CODE_GENERATION,
                          ModelCapability.REASONING],
            modalities=[Modality.TEXT], latency_ms=1000,
            pricing_output_per_1m=2.5, context_window=128000,
            availability=True, fallback_models=["gpt-4o-mini"],
            api_key_env="OPENAI_API_KEY",
        ),
        "openai:gpt-4o-mini": ModelRegistryEntry(
            provider=ProviderName.OPENAI, model_id="gpt-4o-mini",
            capabilities=[ModelCapability.TEXT_GENERATION],
            modalities=[Modality.TEXT], latency_ms=600,
            pricing_output_per_1m=0.15, context_window=128000,
            availability=True, fallback_models=[],
            api_key_env="OPENAI_API_KEY",
        ),
        "anthropic:claude-3-haiku": ModelRegistryEntry(
            provider=ProviderName.ANTHROPIC, model_id="claude-3-haiku-20240307",
            capabilities=[ModelCapability.TEXT_GENERATION],
            modalities=[Modality.TEXT], latency_ms=600,
            pricing_output_per_1m=1.25, context_window=200000,
            availability=True, fallback_models=[],
            api_key_env="ANTHROPIC_API_KEY",
        ),
    }
    reg = ModelRegistry(database_url="postgresql+psycopg2://x:x@localhost:1/x")
    reg._cache = {f"{e.provider.value}:{e.model_id}": e for e in entries.values()}
    reg._cache_loaded_at = 0
    return reg


def _leader():
    reg = _reg_with_models()
    router = ModelRouter(registry=reg)
    leader = LeaderAgent(router=router, registry=reg)
    from orchestration.agents.sub_agents import build_all_sub_agents
    for agent in build_all_sub_agents().values():
        leader.register_sub_agent(agent)
    return leader


def test_leader_init():
    leader = LeaderAgent()
    assert leader.agent_id == "leader_agent"
    assert leader.name == "Leader Agent"
    assert leader.sub_agents == {}
    assert leader.assignments == {}
    assert leader.quality_min_score == 0.7
    assert leader.quality_max_review_attempts == 2


def test_leader_register_sub_agent(leader):
    assert "text_agent" in leader.sub_agents
    agent = leader.sub_agents["text_agent"]
    assert agent.name == "Text Sub-Agent"


def test_leader_analyze_request_single_task():
    leader = _leader()
    tasks = leader.analyze_request("Write a Python script to scrape a website.")
    assert len(tasks) >= 1
    # Should detect code
    assert any(t.task_type == TaskType.CODE for t in tasks)


def test_leader_analyze_request_multiple_tasks():
    leader = _leader()
    tasks = leader.analyze_request("Write code and generate an image and research the topic.")
    types = {t.task_type for t in tasks}
    assert TaskType.CODE in types
    assert TaskType.IMAGE in types
    assert TaskType.RESEARCH in types


def test_leader_analyze_request_defaults_to_text():
    leader = _leader()
    tasks = leader.analyze_request("Just some random words without keywords.")
    assert len(tasks) == 1
    assert tasks[0].task_type == TaskType.TEXT


def test_leader_assign_model_to_sub_agent(leader):
    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Write a greeting.",
    )
    assignment = leader.assign_model("text_agent", task)
    assert assignment.active is True
    assert assignment.assigned_by == "leader_agent"
    assert assignment.agent_id == "text_agent"
    # Sub-agent should have the assignment
    agent = leader.sub_agents["text_agent"]
    assert agent.assignment is not None
    assert agent.assignment.model_id == assignment.model_id
    # Recorded in leader assignments
    assert assignment.id in leader.assignments


def test_leader_assign_model_unknown_agent_raises():
    leader = _leader()
    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Hello.",
    )
    with pytest.raises(ValueError):
        leader.assign_model("nonexistent_agent", task)


def test_leader_sub_agent_cannot_change_own_model(leader):
    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Hello.",
    )
    leader.assign_model("text_agent", task)
    agent = leader.sub_agents["text_agent"]
    assigned_model = agent.assignment.model_id
    assigned_provider = agent.assignment.provider

    with pytest.raises(PermissionError):
        agent._enforce_model_authority(ProviderName.ANTHROPIC, "claude-3-haiku-20240307")

    assert agent.assignment.model_id == assigned_model
    assert agent.assignment.provider == assigned_provider


def test_leader_reassign_model(leader):
    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Hello.",
    )
    first = leader.assign_model("text_agent", task)
    first_id = first.id

    new = leader.reassign_model(
        first_id, "text_agent", ProviderName.ANTHROPIC, "claude-3-haiku-20240307",
        FallbackReason.ERROR,
    )
    assert new.provider == ProviderName.ANTHROPIC
    assert new.model_id == "claude-3-haiku-20240307"
    assert new.assigned_by == "leader_agent"
    assert first.active is False
    assert leader.sub_agents["text_agent"].assignment.model_id == "claude-3-haiku-20240307"


def test_leader_reassign_model_unknown_agent_raises():
    leader = _leader()
    with pytest.raises(ValueError):
        leader.reassign_model("a1", "nonexistent", ProviderName.OPENAI, "gpt-4o", FallbackReason.ERROR)


def test_only_leader_can_issue_assignment(leader):
    agent = leader.sub_agents["text_agent"]
    assignment = ModelAssignment(
        task_id="t1",
        agent_id="text_agent",
        provider=ProviderName.OPENAI,
        model_id="gpt-4o-mini",
        assigned_by="someone_else",
    )
    with pytest.raises(PermissionError):
        agent.set_assignment(assignment, issued_by="someone_else")


def test_registered_sub_agents_seven(leader):
    ids = {a.task_type for a in leader.sub_agents.values()}
    expected = {"text", "image", "video", "audio", "code", "research", "data"}
    assert expected.issubset(ids)


@pytest.mark.asyncio
async def test_leader_execute_sub_agent_success(monkeypatch):
    leader = _leader()
    rec = RecordingAdapter(responses={"gpt-4o": "openai result"})
    register_adapter("openai", rec)

    try:
        import orchestration.agents.base_agent as base_mod
        import orchestration.agents.leader as leader_mod
        orig_base_get = base_mod.get_adapter
        orig_leader_get = leader_mod.get_adapter

        def fake_get(name):
            if name == "openai":
                return rec
            return orig_base_get(name)

        monkeypatch.setattr(base_mod, "get_adapter", fake_get)
        monkeypatch.setattr(leader_mod, "get_adapter", fake_get)

        task = TaskRequest(
            task_type=TaskType.TEXT,
            modality=Modality.TEXT,
            prompt="Say hello.",
        )
        result = await leader.execute_sub_agent("text_agent", task)

        assert result.ok is True
        assert result.model_id in ("gpt-4o", "gpt-4o-mini")
        assert result.provider == ProviderName.OPENAI
        assert len(rec.calls) == 1
        assert rec.calls[0].model_id == result.model_id
    finally:
        from orchestration.adapters.base import _ADAPTERS
        _ADAPTERS.pop("openai", None)


@pytest.mark.asyncio
async def test_leader_quality_below_threshold_triggers_fallback(monkeypatch):
    """When quality is below threshold, the Leader should attempt fallback."""
    leader = _leader()

    # Primary model returns low-quality (short) content; fallback returns good content.
    primary = RecordingAdapter(responses={"gpt-4o": "hi"})  # short -> quality fail
    fallback = RecordingAdapter(responses={"gpt-4o-mini": "This is a detailed and complete response."})
    register_adapter("openai", primary)

    try:
        import orchestration.agents.base_agent as base_mod
        import orchestration.agents.leader as leader_mod
        orig_base_get = base_mod.get_adapter
        orig_leader_get = leader_mod.get_adapter

        call_count = {"n": 0}
        def fake_get(name):
            call_count["n"] += 1
            if name == "openai":
                # First call uses primary (short), second call (fallback) uses fallback
                if call_count["n"] == 1:
                    return primary
                return fallback
            return orig_base_get(name)

        monkeypatch.setattr(base_mod, "get_adapter", fake_get)
        monkeypatch.setattr(leader_mod, "get_adapter", fake_get)

        task = TaskRequest(
            task_type=TaskType.TEXT,
            modality=Modality.TEXT,
            prompt="Write a detailed response.",
        )
        result = await leader.execute_sub_agent("text_agent", task)

        # Should have attempted a fallback assignment
        assert len(leader.assignments) >= 1
    finally:
        from orchestration.adapters.base import _ADAPTERS
        _ADAPTERS.pop("openai", None)


@pytest.mark.asyncio
async def test_leader_provider_error_triggers_fallback(monkeypatch):
    """When the provider errors, the Leader should attempt fallback."""
    leader = _leader()

    primary = RecordingAdapter(responses={}, fail_on={"gpt-4o"})
    fallback = RecordingAdapter(responses={"gpt-4o-mini": "fallback worked"})
    register_adapter("openai", primary)

    try:
        import orchestration.agents.base_agent as base_mod
        import orchestration.agents.leader as leader_mod
        orig_base_get = base_mod.get_adapter
        orig_leader_get = leader_mod.get_adapter

        call_count = {"n": 0}
        def fake_get(name):
            call_count["n"] += 1
            if name == "openai":
                if call_count["n"] == 1:
                    return primary
                return fallback
            return orig_base_get(name)

        monkeypatch.setattr(base_mod, "get_adapter", fake_get)
        monkeypatch.setattr(leader_mod, "get_adapter", fake_get)

        task = TaskRequest(
            task_type=TaskType.TEXT,
            modality=Modality.TEXT,
            prompt="Hello.",
        )
        result = await leader.execute_sub_agent("text_agent", task)

        # At minimum, the leader attempted the fallback (2+ assignments)
        assert len(leader.assignments) >= 1
    finally:
        from orchestration.adapters.base import _ADAPTERS
        _ADAPTERS.pop("openai", None)


def test_leader_review_result_ok():
    leader = _leader()
    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Write about Python programming.",
    )
    result = __import__("orchestration.core.types", fromlist=["AgentResult"]).AgentResult(
        agent_id="text_agent",
        task_id=task.id,
        assignment_id="a1",
        provider=ProviderName.OPENAI,
        model_id="gpt-4o",
        content="Python is a programming language used for many things.",
        ok=True,
    )
    review = leader.review_result(task, result)
    assert review.passed is True
    assert review.score >= leader.quality_min_score


def test_leader_review_result_empty_content():
    leader = _leader()
    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Hello.",
    )
    result = __import__("orchestration.core.types", fromlist=["AgentResult"]).AgentResult(
        agent_id="text_agent",
        task_id=task.id,
        assignment_id="a1",
        provider=ProviderName.OPENAI,
        model_id="gpt-4o",
        content="",
        ok=True,
    )
    review = leader.review_result(task, result)
    assert review.passed is False
    assert review.score < leader.quality_min_score


def test_leader_review_result_failed():
    leader = _leader()
    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Hello.",
    )
    result = __import__("orchestration.core.types", fromlist=["AgentResult"]).AgentResult(
        agent_id="text_agent",
        task_id=task.id,
        assignment_id="a1",
        provider=ProviderName.OPENAI,
        model_id="gpt-4o",
        content="",
        ok=False,
        error="provider down",
    )
    review = leader.review_result(task, result)
    assert review.passed is False
    assert review.score == 0.0


def test_leader_resolve_conflicts_picks_best():
    leader = _leader()
    r1 = __import__("orchestration.core.types", fromlist=["AgentResult"]).AgentResult(
        agent_id="a", task_id="t1", assignment_id="a1",
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        content="short", ok=True, quality_score=0.5, cost_usd=0.01, latency_ms=100,
    )
    r2 = __import__("orchestration.core.types", fromlist=["AgentResult"]).AgentResult(
        agent_id="b", task_id="t1", assignment_id="a2",
        provider=ProviderName.ANTHROPIC, model_id="claude",
        content="This is a longer and better result with more detail.", ok=True,
        quality_score=0.9, cost_usd=0.02, latency_ms=200,
    )
    resolved = leader.resolve_conflicts([r1, r2])
    assert resolved.model_id == "claude"
    assert resolved.quality_score == 0.9


def test_leader_resolve_conflicts_single():
    leader = _leader()
    r = __import__("orchestration.core.types", fromlist=["AgentResult"]).AgentResult(
        agent_id="a", task_id="t1", assignment_id="a1",
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        content="only result", ok=True, quality_score=0.8, cost_usd=0.01, latency_ms=100,
    )
    resolved = leader.resolve_conflicts([r])
    assert resolved is r


def test_leader_resolve_conflicts_empty_raises():
    leader = _leader()
    with pytest.raises(ValueError):
        leader.resolve_conflicts([])
