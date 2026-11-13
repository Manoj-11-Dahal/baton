"""Tests for core/types.py — shared data types."""
from datetime import datetime

import pytest
from pydantic import ValidationError

from orchestration.core.types import (
    AgentResult,
    AuditEvent,
    FallbackReason,
    ModelAssignment,
    ModelAssignmentUpdate,
    ModelCapability,
    ModelRegistryEntry,
    Modality,
    ProviderName,
    QualityReview,
    RouterDecision,
    SecurityContext,
    TaskRequest,
    TaskType,
)


def test_task_type_enum():
    assert TaskType.TEXT == "text"
    assert TaskType.IMAGE == "image"
    assert TaskType.VIDEO == "video"
    assert TaskType.AUDIO == "audio"
    assert TaskType.CODE == "code"
    assert TaskType.RESEARCH == "research"
    assert TaskType.DATA == "data"


def test_modality_enum():
    assert Modality.TEXT == "text"
    assert Modality.IMAGE == "image"
    assert Modality.VIDEO == "video"
    assert Modality.AUDIO == "audio"
    assert Modality.CODE == "code"
    assert Modality.EMBEDDING == "embedding"
    assert Modality.MULTIMODAL == "multimodal"
    assert Modality.SPEECH == "speech"


def test_provider_name_enum():
    assert ProviderName.OPENAI == "openai"
    assert ProviderName.ANTHROPIC == "anthropic"
    assert ProviderName.GOOGLE == "google"
    assert ProviderName.GEMINI == "gemini"
    assert ProviderName.LLAMA == "llama"
    assert ProviderName.MISTRAL == "mistral"
    assert ProviderName.DEEPSEEK == "deepseek"
    assert ProviderName.QWEN == "qwen"
    assert ProviderName.LOCAL == "local"


def test_model_capability_enum():
    assert ModelCapability.TEXT_GENERATION == "text_generation"
    assert ModelCapability.IMAGE_GENERATION == "image_generation"
    assert ModelCapability.VIDEO_GENERATION == "video_generation"
    assert ModelCapability.AUDIO_GENERATION == "audio_generation"
    assert ModelCapability.CODE_GENERATION == "code_generation"
    assert ModelCapability.REASONING == "reasoning"
    assert ModelCapability.EMBEDDINGS == "embeddings"
    assert ModelCapability.MULTIMODAL_INPUT == "multimodal_input"
    assert ModelCapability.FUNCTION_CALLING == "function_calling"
    assert ModelCapability.JSON_OUTPUT == "json_output"
    assert ModelCapability.LONG_CONTEXT == "long_context"


def test_fallback_reason_enum():
    assert FallbackReason.RATE_LIMIT == "rate_limit"
    assert FallbackReason.ERROR == "error"
    assert FallbackReason.TIMEOUT == "timeout"
    assert FallbackReason.UNAVAILABLE == "unavailable"
    assert FallbackReason.QUALITY_THRESHOLD == "quality_threshold"
    assert FallbackReason.CONTEXT_EXCEEDED == "context_exceeded"


def test_task_request_defaults():
    t = TaskRequest(task_type="text", prompt="hello")
    assert t.task_type == TaskType.TEXT
    assert t.modality == Modality.TEXT
    assert t.prompt == "hello"
    assert t.context == {}
    assert t.required_capabilities == []
    assert t.preferred_provider is None
    assert t.blocked_providers == []
    assert t.max_cost_usd is None
    assert t.min_quality_score is None
    assert t.timeout_sec is None
    assert t.max_retries is None
    assert t.metadata == {}
    assert isinstance(t.id, str)
    assert isinstance(t.created_at, datetime)


def test_model_assignment_defaults():
    a = ModelAssignment(
        task_id="t1",
        agent_id="agent1",
        provider=ProviderName.OPENAI,
        model_id="gpt-4o",
    )
    assert a.task_id == "t1"
    assert a.agent_id == "agent1"
    assert a.provider == ProviderName.OPENAI
    assert a.model_id == "gpt-4o"
    assert a.base_url is None
    assert a.api_key_env is None
    assert a.capabilities == []
    assert a.context_window is None
    assert a.estimated_cost_usd is None
    assert a.timeout_sec == 120
    assert a.max_retries == 3
    assert a.fallback_assignments == []
    assert a.assigned_by == "leader_agent"
    assert a.active is True
    assert isinstance(a.id, str)
    assert isinstance(a.assigned_at, datetime)


def test_model_assignment_update():
    u = ModelAssignmentUpdate(
        assignment_id="a1",
        task_id="t1",
        agent_id="agent1",
        provider=ProviderName.ANTHROPIC,
        model_id="claude-3-haiku",
        reason=FallbackReason.ERROR,
    )
    assert u.assignment_id == "a1"
    assert u.provider == ProviderName.ANTHROPIC
    assert u.model_id == "claude-3-haiku"
    assert u.reason == FallbackReason.ERROR
    assert u.assigned_by == "leader_agent"


def test_agent_result_defaults():
    r = AgentResult(
        agent_id="agent1",
        task_id="t1",
        assignment_id="a1",
        provider=ProviderName.OPENAI,
        model_id="gpt-4o",
        content="hello world",
    )
    assert r.agent_id == "agent1"
    assert r.content == "hello world"
    assert r.structured is None
    assert r.usage == {}
    assert r.latency_ms == 0
    assert r.cost_usd == 0.0
    assert r.quality_score is None
    assert r.ok is True
    assert r.error is None
    assert r.fallback_used is False
    assert r.fallback_reason is None
    assert r.retry_count == 0


def test_quality_review():
    q = QualityReview(
        task_id="t1",
        assignment_id="a1",
        reviewer_agent="leader_agent",
        score=0.8,
        passed=True,
        feedback="looks good",
        issues=[],
        requires_rework=False,
    )
    assert q.score == 0.8
    assert q.passed is True
    assert q.feedback == "looks good"
    assert q.requires_rework is False


def test_quality_review_score_bounds():
    with pytest.raises(ValidationError):
        QualityReview(
            task_id="t1",
            assignment_id="a1",
            reviewer_agent="leader_agent",
            score=1.5,  # > 1.0
            passed=True,
        )
    with pytest.raises(ValidationError):
        QualityReview(
            task_id="t1",
            assignment_id="a1",
            reviewer_agent="leader_agent",
            score=-0.1,  # < 0.0
            passed=True,
        )


def test_audit_event():
    e = AuditEvent(
        actor="leader_agent",
        action="model_assigned",
        target="gpt-4o",
        details={"agent_id": "a1"},
        ok=True,
    )
    assert e.actor == "leader_agent"
    assert e.action == "model_assigned"
    assert e.target == "gpt-4o"
    assert e.ok is True
    assert e.error is None
    assert isinstance(e.id, str)
    assert isinstance(e.timestamp, datetime)


def test_security_context_defaults():
    sc = SecurityContext()
    assert sc.user_id is None
    assert isinstance(sc.session_id, str)
    assert sc.allowed_tools == []
    assert sc.denied_tools == []
    assert sc.sandbox is True
    assert sc.sandbox_timeout_sec == 30
    assert sc.sandbox_max_memory_mb == 512
    assert sc.audit_enabled is True


def test_model_registry_entry():
    e = ModelRegistryEntry(
        provider=ProviderName.GEMINI,
        model_id="gemini-2.0-flash",
        capabilities=[ModelCapability.TEXT_GENERATION, ModelCapability.CODE_GENERATION],
        modalities=[Modality.TEXT, Modality.IMAGE, Modality.AUDIO, Modality.MULTIMODAL],
        context_window=1000000,
        pricing_input_per_1m=0.10,
        pricing_output_per_1m=0.40,
        latency_ms=800,
        availability=True,
        fallback_models=["gemini-1.5-flash"],
        api_key_env="GEMINI_API_KEY",
    )
    assert e.provider == ProviderName.GEMINI
    assert e.model_id == "gemini-2.0-flash"
    assert ModelCapability.CODE_GENERATION in e.capabilities
    assert Modality.AUDIO in e.modalities
    assert e.context_window == 1000000
    assert e.enabled is True


def test_router_decision():
    rd = RouterDecision(
        task_id="t1",
        provider=ProviderName.OPENAI,
        model_id="gpt-4o-mini",
        rationale="low cost and fast",
        scored_options=[],
    )
    assert rd.provider == ProviderName.OPENAI
    assert rd.model_id == "gpt-4o-mini"
    assert rd.rationale == "low cost and fast"
    assert rd.fallback_chain == []
    assert rd.estimated_cost_usd is None
    assert rd.estimated_latency_ms is None
