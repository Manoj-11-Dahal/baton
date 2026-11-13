"""Tests for orchestration/engine.py — LangGraph Orchestration Engine."""
import asyncio

import pytest

from orchestration.agents.leader import LeaderAgent
from orchestration.core.types import TaskRequest, TaskType
from orchestration.orchestration.engine import OrchestrationEngine


def test_engine_init_registers_sub_agents():
    leader = LeaderAgent()
    engine = OrchestrationEngine(leader=leader)
    ids = {a.task_type for a in leader.sub_agents.values()}
    expected = {"text", "image", "video", "audio", "code", "research", "data"}
    assert expected.issubset(ids)
    assert engine.graph is not None


def test_engine_analyze_node():
    leader = LeaderAgent()
    engine = OrchestrationEngine(leader=leader)
    from orchestration.orchestration.engine import OrchestrationState
    state = OrchestrationState(user_request="Write code and generate an image.")
    result = asyncio.run(engine._analyze_node(state))
    types = {t.task_type for t in result.tasks}
    assert TaskType.CODE in types
    assert TaskType.IMAGE in types


def test_engine_execute_node_sequential(monkeypatch):
    """execute_node should run tasks sequentially when sequential=True."""
    leader = LeaderAgent()
    engine = OrchestrationEngine(leader=leader, max_parallel_subagents=2)
    from orchestration.orchestration.engine import OrchestrationState

    # Force a single task so execution is simple
    state = OrchestrationState(
        user_request="Say hello.",
        sequential=True,
    )
    state.tasks = [
        TaskRequest(task_type=TaskType.TEXT, modality="text", prompt="Say hello.")
    ]
    # Monkeypatch execute_sub_agent to avoid real provider calls
    async def fake_execute(agent_id, task):
        from orchestration.core.types import AgentResult, ProviderName
        return AgentResult(
            agent_id=agent_id, task_id=task.id, assignment_id="a1",
            provider=ProviderName.OPENAI, model_id="gpt-4o",
            content="hello", ok=True,
        )
    leader.execute_sub_agent = fake_execute

    result = asyncio.run(engine._execute_node(state))
    assert len(result.results) == 1
    assert result.results[0].content == "hello"


def test_engine_review_node():
    leader = LeaderAgent()
    engine = OrchestrationEngine(leader=leader)
    from orchestration.orchestration.engine import OrchestrationState
    from orchestration.core.types import AgentResult, ProviderName

    state = OrchestrationState(user_request="test")
    state.results = [
        AgentResult(
            agent_id="a1", task_id="t1", assignment_id="a1",
            provider=ProviderName.OPENAI, model_id="gpt-4o",
            content="result one", ok=True, quality_score=0.9,
        ),
        AgentResult(
            agent_id="a2", task_id="t1", assignment_id="a2",
            provider=ProviderName.ANTHROPIC, model_id="claude",
            content="result two shorter", ok=True, quality_score=0.4,
        ),
    ]
    result = asyncio.run(engine._review_node(state))
    assert result.final is not None
    # Should pick the higher quality result as the base
    assert result.final.content.startswith("result one")


def test_engine_review_node_no_results():
    leader = LeaderAgent()
    engine = OrchestrationEngine(leader=leader)
    from orchestration.orchestration.engine import OrchestrationState
    state = OrchestrationState(user_request="test")
    result = asyncio.run(engine._review_node(state))
    assert result.error == "No results produced during execution."


def test_engine_finalize_node_records_result():
    leader = LeaderAgent()
    engine = OrchestrationEngine(leader=leader)
    from orchestration.orchestration.engine import OrchestrationState
    from orchestration.core.types import AgentResult, ProviderName

    state = OrchestrationState(user_request="test")
    state.final = AgentResult(
        agent_id="a1", task_id="t1", assignment_id="a1",
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        content="final", ok=True,
    )
    result = asyncio.run(engine._finalize_node(state))
    # finalize should not crash and should record the result
    assert result.final is not None


def test_engine_run_returns_dict():
    leader = LeaderAgent()
    engine = OrchestrationEngine(leader=leader)
    # Mock execute_sub_agent to avoid real provider calls
    async def fake_execute(agent_id, task):
        from orchestration.core.types import AgentResult, ProviderName
        return AgentResult(
            agent_id=agent_id, task_id=task.id, assignment_id="a1",
            provider=ProviderName.OPENAI, model_id="gpt-4o",
            content="done", ok=True,
        )
    leader.execute_sub_agent = fake_execute

    result = asyncio.run(
        engine.run("Say hello.", sequential=True)
    )
    assert "user_request" in result
    assert result["user_request"] == "Say hello."
    assert "results" in result
    assert "final" in result
    assert "elapsed_ms" in result
    assert "assignments" in result
