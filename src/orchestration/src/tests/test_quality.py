"""Tests for quality/quality.py — Quality Control and Fallback system."""
import asyncio

import pytest

from orchestration.adapters.base import ModelCall, get_adapter, register_adapter
from orchestration.core.types import (
    AgentResult,
    ModelCapability,
    Modality,
    ProviderName,
    TaskRequest,
    TaskType,
)
from orchestration.quality.quality import QualityController, get_quality_controller


class RecordingAdapter:
    def __init__(self, content="pass", ok=True):
        self.content = content
        self.ok = ok
        self.calls = []

    async def call(self, call: ModelCall):
        self.calls.append(call)
        from orchestration.adapters.base import ModelResponse
        return ModelResponse(
            model_id=call.model_id,
            provider=call.provider,
            content=self.content,
            ok=self.ok,
        )


def test_quality_controller_init():
    qc = QualityController()
    assert qc.leader_agent_id == "leader_agent"
    assert qc.min_score == 0.7
    assert qc.max_review_attempts == 2
    assert qc.history == []


def test_quality_controller_review_pass():
    qc = QualityController()
    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Write about Python.",
    )
    result = AgentResult(
        agent_id="agent1",
        task_id=task.id,
        assignment_id="a1",
        provider=ProviderName.OPENAI,
        model_id="gpt-4o",
        content="Python is a programming language used for many things.",
        ok=True,
    )
    review = qc.review(task, result)
    assert review.passed is True
    assert review.score >= qc.min_score
    assert review.requires_rework is False
    assert len(qc.history) == 1


def test_quality_controller_review_fail_empty():
    qc = QualityController()
    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Hello.",
    )
    result = AgentResult(
        agent_id="agent1",
        task_id=task.id,
        assignment_id="a1",
        provider=ProviderName.OPENAI,
        model_id="gpt-4o",
        content="",
        ok=True,
    )
    review = qc.review(task, result)
    assert review.passed is False
    assert review.score < qc.min_score
    assert review.requires_rework is True


def test_quality_controller_review_fail_execution_error():
    qc = QualityController()
    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Hello.",
    )
    result = AgentResult(
        agent_id="agent1",
        task_id=task.id,
        assignment_id="a1",
        provider=ProviderName.OPENAI,
        model_id="gpt-4o",
        content="",
        ok=False,
        error="provider down",
    )
    review = qc.review(task, result)
    assert review.passed is False
    assert review.score == 0.0


def test_quality_controller_should_fallback():
    qc = QualityController(max_review_attempts=2)
    # Create a failed review
    task = TaskRequest(task_type=TaskType.TEXT, modality=Modality.TEXT, prompt="x")
    result = AgentResult(
        agent_id="a", task_id=task.id, assignment_id="a1",
        provider=ProviderName.OPENAI, model_id="gpt-4o", content="",
        ok=True,
    )
    review = qc.review(task, result)
    assert qc.should_fallback(review, attempt=0) is True
    assert qc.should_fallback(review, attempt=1) is True
    assert qc.should_fallback(review, attempt=2) is False  # max attempts reached

    # A passing review should not trigger fallback
    task2 = TaskRequest(task_type=TaskType.TEXT, modality=Modality.TEXT, prompt="Python programming")
    result2 = AgentResult(
        agent_id="a", task_id=task2.id, assignment_id="a1",
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        content="Python is a programming language used for many things.",
        ok=True,
    )
    review2 = qc.review(task2, result2)
    assert qc.should_fallback(review2, attempt=0) is False


def test_quality_controller_summarize_empty():
    qc = QualityController()
    summary = qc.summarize()
    assert summary == {
        "reviews": 0,
        "passed": 0,
        "failed": 0,
        "avg_score": 0.0,
    }


def test_quality_controller_summarize_with_history():
    qc = QualityController()
    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Python programming language details",
    )
    # One pass - content matches prompt well
    r1 = AgentResult(
        agent_id="a", task_id=task.id, assignment_id="a1",
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        content="Python is a programming language used for many things.",
        ok=True,
    )
    qc.review(task, r1)
    # One fail
    r2 = AgentResult(
        agent_id="a", task_id=task.id, assignment_id="a1",
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        content="",
        ok=True,
    )
    qc.review(task, r2)
    summary = qc.summarize()
    assert summary["reviews"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert 0.0 <= summary["avg_score"] <= 1.0


def test_get_quality_controller_singleton():
    qc1 = get_quality_controller()
    qc2 = get_quality_controller()
    assert qc1 is qc2


@pytest.mark.asyncio
async def test_quality_controller_llm_judge_review(monkeypatch):
    """llm_judge_review should use the adapter and return a review."""
    qc = QualityController()
    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Hello.",
    )
    result = AgentResult(
        agent_id="a", task_id=task.id, assignment_id="a1",
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        content="some content", ok=True,
    )
    rec = RecordingAdapter(content="PASS")
    register_adapter("openai", rec)

    try:
        import orchestration.quality.quality as q_mod
        orig_get = q_mod.get_adapter

        def fake_get(name):
            if name == "openai":
                return rec
            return orig_get(name)

        monkeypatch.setattr(q_mod, "get_adapter", fake_get)

        judge_call = ModelCall(
            model_id="gpt-4o", provider=ProviderName.OPENAI,
            messages=[{"role": "user", "content": "judge this"}],
        )
        review = await qc.llm_judge_review(task, result, judge_call)

        assert review.passed is True
        assert review.score == 1.0
        assert "PASS" in review.feedback
    finally:
        from orchestration.adapters.base import _ADAPTERS
        _ADAPTERS.pop("openai", None)


@pytest.mark.asyncio
async def test_quality_controller_llm_judge_review_fallback_on_error(monkeypatch):
    """llm_judge_review should fall back to heuristic review on adapter error."""
    qc = QualityController()
    task = TaskRequest(task_type=TaskType.TEXT, modality=Modality.TEXT, prompt="x")
    result = AgentResult(
        agent_id="a", task_id=task.id, assignment_id="a1",
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        content="", ok=True,
    )
    rec = RecordingAdapter()
    # Force an exception
    async def boom(call):
        raise RuntimeError("adapter down")
    rec.call = boom
    register_adapter("openai", rec)

    try:
        import orchestration.quality.quality as q_mod
        orig_get = q_mod.get_adapter
        monkeypatch.setattr(q_mod, "get_adapter", lambda name: rec)

        judge_call = ModelCall(
            model_id="gpt-4o", provider=ProviderName.OPENAI,
            messages=[{"role": "user", "content": "judge this"}],
        )
        review = await qc.llm_judge_review(task, result, judge_call)

        # Should fall back to heuristic review (empty content -> fail)
        assert review.passed is False
    finally:
        from orchestration.adapters.base import _ADAPTERS
        _ADAPTERS.pop("openai", None)
