"""Observability: OpenTelemetry tracing, metrics, and cost/latency tracking.

Tracks model assignments, token usage, cost, latency, errors, retries, and
quality metrics. Exports to an OTLP endpoint when configured; otherwise works
as a no-op local recorder.
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from .config import get_settings
from .types import AgentResult, ModelAssignment


@dataclass
class SpanRecord:
    name: str
    start_ms: float
    end_ms: float = 0.0
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "ok"  # ok | error


class Observability:
    """Records telemetry for orchestration runs.

    Uses OpenTelemetry when an exporter endpoint is configured; otherwise falls
    back to an in-memory span recorder so tests and local runs still work.
    """

    def __init__(self, service_name: Optional[str] = None, endpoint: Optional[str] = None):
        settings = get_settings()
        self.service_name = service_name or settings.otel_service_name
        self.endpoint = endpoint or settings.otel_exporter_otlp_endpoint
        self._spans: List[SpanRecord] = []
        self._tracer = None
        self._initialized = False

    def _ensure(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        try:
            resource = Resource.create({"service.name": self.service_name})
            provider = TracerProvider(resource=resource)
            otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or self.endpoint
            if otlp_endpoint and otlp_endpoint != "http://localhost:4318":
                try:
                    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                        OTLPSpanExporter,
                    )
                    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
                except Exception:  # noqa: BLE001
                    pass
            else:
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer(__name__)
        except Exception:  # noqa: BLE001
            self._tracer = None

    @property
    def tracer(self):
        self._ensure()
        return self._tracer

    # ------------------------------------------------------------------ tracing

    @contextmanager
    def span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        attrs = dict(attributes or {})
        record = SpanRecord(name=name, start_ms=time.time() * 1000, attributes=attrs)
        otel_span = None
        if self.tracer:
            otel_span = self.tracer.start_span(name)
            if attrs:
                otel_span.set_attributes(attrs)
        try:
            yield record
            record.status = "ok"
        except Exception as exc:  # noqa: BLE001
            record.status = "error"
            record.events.append({"name": "error", "attributes": {"error": str(exc)}})
            raise
        finally:
            record.end_ms = time.time() * 1000
            self._spans.append(record)
            if otel_span:
                otel_span.set_attribute("status", record.status)
                otel_span.set_attribute("latency_ms", record.end_ms - record.start_ms)
                otel_span.end()

    # --------------------------------------------------------------- metrics

    def record_model_assignment(self, assignment: ModelAssignment) -> None:
        self._spans.append(
            SpanRecord(
                name="model.assignment",
                start_ms=0.0,
                end_ms=0.0,
                attributes={
                    "assignment_id": assignment.id,
                    "task_id": assignment.task_id,
                    "agent_id": assignment.agent_id,
                    "provider": assignment.provider,
                    "model_id": assignment.model_id,
                    "assigned_by": assignment.assigned_by,
                    "active": assignment.active,
                },
            )
        )

    def record_agent_result(self, result: AgentResult) -> None:
        self._spans.append(
            SpanRecord(
                name="agent.result",
                start_ms=0.0,
                end_ms=float(result.latency_ms),
                attributes={
                    "agent_id": result.agent_id,
                    "task_id": result.task_id,
                    "assignment_id": result.assignment_id,
                    "provider": result.provider,
                    "model_id": result.model_id,
                    "ok": result.ok,
                    "fallback_used": result.fallback_used,
                    "fallback_reason": result.fallback_reason or "",
                    "retry_count": result.retry_count,
                    "cost_usd": result.cost_usd,
                    "quality_score": result.quality_score or 0.0,
                    "latency_ms": result.latency_ms,
                    "usage": result.usage,
                },
                status="ok" if result.ok else "error",
            )
        )

    def record_cost(self, task_id: str, model_id: str, provider: str, cost_usd: float) -> None:
        self._spans.append(
            SpanRecord(
                name="cost",
                start_ms=0.0,
                end_ms=0.0,
                attributes={
                    "task_id": task_id,
                    "model_id": model_id,
                    "provider": provider,
                    "cost_usd": cost_usd,
                },
            )
        )

    def record_quality(self, task_id: str, score: float, passed: bool) -> None:
        self._spans.append(
            SpanRecord(
                name="quality",
                start_ms=0.0,
                end_ms=0.0,
                attributes={
                    "task_id": task_id,
                    "quality_score": score,
                    "passed": passed,
                },
            )
        )

    def get_spans(self) -> List[SpanRecord]:
        return list(self._spans)


# Module-level singleton so every module can import the same instance.
_observability: Optional[Observability] = None


def get_observability() -> Observability:
    global _observability
    if _observability is None:
        _observability = Observability()
    return _observability
