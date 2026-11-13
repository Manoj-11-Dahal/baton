"""Tests for core/observability.py — OpenTelemetry tracing/metrics."""
import pytest

from orchestration.core.observability import Observability, SpanRecord, get_observability
from orchestration.core.types import AgentResult, ModelAssignment, ProviderName


def test_span_record_defaults():
    """SpanRecord should default end_ms to 0.0 and status to 'ok'."""
    sr = SpanRecord(name="test", start_ms=100.0)
    assert sr.name == "test"
    assert sr.start_ms == 100.0
    assert sr.end_ms == 0.0
    assert sr.attributes == {}
    assert sr.events == []
    assert sr.status == "ok"


def test_observability_span_ok():
    """span() context manager should record a successful span."""
    obs = Observability()
    with obs.span("test_span", attributes={"key": "value"}) as record:
        assert record.name == "test_span"
        assert record.attributes == {"key": "value"}
    assert record.end_ms > 0
    assert record.status == "ok"
    spans = obs.get_spans()
    assert len(spans) == 1
    assert spans[0].name == "test_span"


def test_observability_span_error():
    """span() context manager should record an error span on exception."""
    obs = Observability()
    with pytest.raises(ValueError):
        with obs.span("failing_span"):
            raise ValueError("boom")
    spans = obs.get_spans()
    assert len(spans) == 1
    assert spans[0].status == "error"
    assert len(spans[0].events) == 1
    assert spans[0].events[0]["name"] == "error"


def test_observability_record_model_assignment():
    """record_model_assignment should add a span."""
    obs = Observability()
    a = ModelAssignment(
        task_id="t1",
        agent_id="agent1",
        provider=ProviderName.OPENAI,
        model_id="gpt-4o",
    )
    obs.record_model_assignment(a)
    spans = obs.get_spans()
    assert len(spans) == 1
    assert spans[0].name == "model.assignment"
    assert spans[0].attributes["assignment_id"] == a.id
    assert spans[0].attributes["provider"] == "openai"


def test_observability_record_agent_result():
    """record_agent_result should add a span with result attributes."""
    obs = Observability()
    r = AgentResult(
        agent_id="agent1",
        task_id="t1",
        assignment_id="a1",
        provider=ProviderName.OPENAI,
        model_id="gpt-4o",
        content="hi",
        ok=True,
        latency_ms=150,
        cost_usd=0.002,
        quality_score=0.9,
    )
    obs.record_agent_result(r)
    spans = obs.get_spans()
    assert len(spans) == 1
    assert spans[0].name == "agent.result"
    assert spans[0].attributes["ok"] is True
    assert spans[0].attributes["quality_score"] == 0.9


def test_observability_record_cost():
    """record_cost should add a cost span."""
    obs = Observability()
    obs.record_cost("t1", "gpt-4o", "openai", 0.05)
    spans = obs.get_spans()
    assert len(spans) == 1
    assert spans[0].name == "cost"
    assert spans[0].attributes["cost_usd"] == 0.05


def test_observability_record_quality():
    """record_quality should add a quality span."""
    obs = Observability()
    obs.record_quality("t1", 0.85, True)
    spans = obs.get_spans()
    assert len(spans) == 1
    assert spans[0].name == "quality"
    assert spans[0].attributes["quality_score"] == 0.85
    assert spans[0].attributes["passed"] is True


def test_get_observability_singleton():
    """get_observability should return a cached singleton."""
    o1 = get_observability()
    o2 = get_observability()
    assert o1 is o2


def test_observability_span_without_tracer():
    """span() should work even when OpenTelemetry tracer is not configured."""
    obs = Observability()
    # Force re-init without tracer by clearing
    obs._initialized = False
    obs._tracer = None
    with obs.span("noop_span") as record:
        pass
    assert len(obs.get_spans()) == 1
