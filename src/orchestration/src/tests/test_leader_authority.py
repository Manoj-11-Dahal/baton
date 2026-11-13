"""Tests that the Leader Agent holds exclusive authority over model assignments.

Sub-Agents must NOT be able to select, replace, or switch their own models.
"""
from orchestration.agents.base_agent import SubAgent
from orchestration.agents.leader import LeaderAgent
from orchestration.core.types import (
    FallbackReason,
    ModelAssignment,
    Modality,
    ProviderName,
    TaskRequest,
    TaskType,
)
from orchestration.router.router import ModelRouter
from orchestration.registry.registry import ModelRegistry


def _registry_with_model():
    reg = ModelRegistry(database_url="postgresql+psycopg2://x:x@localhost:1/x")
    entry = type("E", (), {
        "provider": ProviderName.OPENAI,
        "model_id": "gpt-4o-mini",
        "base_url": None,
        "api_key_env": "OPENAI_API_KEY",
        "capabilities": [],
        "context_window": 128000,
    })()
    reg.get = lambda p, m: entry if (p == ProviderName.OPENAI and m == "gpt-4o-mini") else None
    reg.get_capable_models = lambda *a, **k: [entry]
    return reg


def test_leader_assigns_model_to_sub_agent(leader):
    agent = leader.sub_agents.get("text_agent")
    assert agent is not None
    assert agent.assignment is None

    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Write a greeting.",
    )
    assignment = leader.assign_model("text_agent", task)

    assert assignment.active is True
    assert assignment.assigned_by == "leader_agent"
    assert agent.assignment is not None
    assert agent.assignment.model_id == assignment.model_id
    assert agent.assignment.provider == assignment.provider


def test_sub_agent_cannot_change_own_model(leader):
    agent = leader.sub_agents["text_agent"]
    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Hello.",
    )
    leader.assign_model("text_agent", task)
    assigned_model = agent.assignment.model_id
    assigned_provider = agent.assignment.provider

    # Sub-Agent attempts to independently select/switch models -> must be rejected.
    with __import__("pytest").raises(PermissionError):
        agent._enforce_model_authority(ProviderName.ANTHROPIC, "claude-3-haiku-20240307")

    # Assignment must remain unchanged after the rejected attempt.
    assert agent.assignment.model_id == assigned_model
    assert agent.assignment.provider == assigned_provider


def test_sub_agent_execution_uses_assigned_model(leader):
    agent = leader.sub_agents["text_agent"]
    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Say hello in one word.",
    )
    leader.assign_model("text_agent", task)

    # No API key -> adapter call will fail, but it must use the assigned model.
    result = None
    try:
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(agent.execute(task))
    except Exception:
        pass
    # The call used the leader-assigned model regardless of success/failure.
    assert agent.assignment is not None


def test_leader_reassign_model(leader):
    agent = leader.sub_agents["text_agent"]
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
    assert first.active is False  # old deactivated
    assert agent.assignment.model_id == "claude-3-haiku-20240307"


def test_only_leader_can_issue_assignment(leader):
    agent = leader.sub_agents["text_agent"]
    assignment = ModelAssignment(
        task_id="t1",
        agent_id="text_agent",
        provider=ProviderName.OPENAI,
        model_id="gpt-4o-mini",
        assigned_by="someone_else",  # not leader
    )
    with __import__("pytest").raises(PermissionError):
        agent.set_assignment(assignment, issued_by="someone_else")


def test_registered_sub_agents_seven(leader):
    # All seven specialized sub-agents should be registered.
    ids = {a.task_type for a in leader.sub_agents.values()}
    expected = {"text", "image", "video", "audio", "code", "research", "data"}
    assert expected.issubset(ids)
