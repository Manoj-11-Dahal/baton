"""Shared data types for the orchestration system.

These types are provider-independent and describe tasks, model assignments,
agent results, quality reviews, audit events, and security context.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """Categories of work the system can route to specialized sub-agents."""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    CODE = "code"
    RESEARCH = "research"
    DATA = "data"


class Modality(str, Enum):
    """Input/output modalities a model may support."""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    CODE = "code"
    EMBEDDING = "embedding"
    MULTIMODAL = "multimodal"
    SPEECH = "speech"


class ProviderName(str, Enum):
    """Supported model providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    GEMINI = "gemini"
    LLAMA = "llama"
    MISTRAL = "mistral"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    LOCAL = "local"


class ModelCapability(str, Enum):
    """Capabilities a model may advertise."""
    TEXT_GENERATION = "text_generation"
    CODE_GENERATION = "code_generation"
    REASONING = "reasoning"
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    AUDIO_GENERATION = "audio_generation"
    SPEECH_TO_TEXT = "speech_to_text"
    TEXT_TO_SPEECH = "text_to_speech"
    EMBEDDINGS = "embeddings"
    MULTIMODAL_INPUT = "multimodal_input"
    FUNCTION_CALLING = "function_calling"
    JSON_OUTPUT = "json_output"
    LONG_CONTEXT = "long_context"


class FallbackReason(str, Enum):
    """Why a model was swapped for a fallback."""
    RATE_LIMIT = "rate_limit"
    ERROR = "error"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    QUALITY_THRESHOLD = "quality_threshold"
    CONTEXT_EXCEEDED = "context_exceeded"


# ---------------------------------------------------------------------------
# Request / assignment / result models
# ---------------------------------------------------------------------------


class TaskRequest(BaseModel):
    """A unit of work submitted to the Leader Agent."""
    id: str = Field(default_factory=lambda: uuid4().hex)
    task_type: TaskType
    modality: Modality = Modality.TEXT
    prompt: str
    context: Dict[str, Any] = Field(default_factory=dict)
    required_capabilities: List[ModelCapability] = Field(default_factory=list)
    preferred_provider: Optional[ProviderName] = None
    blocked_providers: List[ProviderName] = Field(default_factory=list)
    max_cost_usd: Optional[float] = None
    min_quality_score: Optional[float] = None
    timeout_sec: Optional[int] = None
    max_retries: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ModelAssignment(BaseModel):
    """The Leader's binding of a sub-agent task to a specific model/provider.

    This is the single source of truth for which model a sub-agent must use.
    Sub-Agents cannot override it.
    """
    id: str = Field(default_factory=lambda: uuid4().hex)
    task_id: str
    agent_id: str
    provider: ProviderName
    model_id: str
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    capabilities: List[ModelCapability] = Field(default_factory=list)
    context_window: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    timeout_sec: int = 120
    max_retries: int = 3
    fallback_assignments: List["ModelAssignment"] = Field(default_factory=list)
    assigned_by: str = "leader_agent"
    assigned_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = True


class ModelAssignmentUpdate(BaseModel):
    """Leader-issued reassignment of a sub-agent to a different model."""
    assignment_id: str
    task_id: str
    agent_id: str
    provider: ProviderName
    model_id: str
    base_url: Optional[str] = None
    reason: FallbackReason
    assigned_by: str = "leader_agent"
    assigned_at: datetime = Field(default_factory=datetime.utcnow)


class AgentResult(BaseModel):
    """Structured result returned by a sub-agent (or the Leader)."""
    agent_id: str
    task_id: str
    assignment_id: str
    provider: ProviderName
    model_id: str
    content: Any
    structured: Optional[Dict[str, Any]] = None
    usage: Dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = 0
    cost_usd: float = 0.0
    quality_score: Optional[float] = None
    ok: bool = True
    error: Optional[str] = None
    fallback_used: bool = False
    fallback_reason: Optional[FallbackReason] = None
    retry_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class QualityReview(BaseModel):
    """Leader quality-control verdict on an agent result."""
    id: str = Field(default_factory=lambda: uuid4().hex)
    task_id: str
    assignment_id: str
    reviewer_agent: str = "leader_agent"
    score: float = Field(ge=0.0, le=1.0)
    passed: bool
    feedback: str = ""
    issues: List[str] = Field(default_factory=list)
    requires_rework: bool = False
    review_at: datetime = Field(default_factory=datetime.utcnow)


class AuditEvent(BaseModel):
    """Immutable audit log entry."""
    id: str = Field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    actor: str  # "leader_agent" | "sub_agent:<id>" | "router" | "system"
    action: str
    target: str  # model id, agent id, task id, etc.
    details: Dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    error: Optional[str] = None


class SecurityContext(BaseModel):
    """Security context for a request (permissions, sandbox, audit)."""
    user_id: Optional[str] = None
    session_id: str = Field(default_factory=lambda: uuid4().hex)
    allowed_tools: List[str] = Field(default_factory=list)
    denied_tools: List[str] = Field(default_factory=list)
    sandbox: bool = True
    sandbox_timeout_sec: int = 30
    sandbox_max_memory_mb: int = 512
    audit_enabled: bool = True


# Rebuild forward references
ModelAssignment.model_rebuild()


class ModelRegistryEntry(BaseModel):
    """A single model entry in the Central Model Registry."""
    provider: ProviderName
    model_id: str
    name: Optional[str] = None
    capabilities: List[ModelCapability] = Field(default_factory=list)
    modalities: List[Modality] = Field(default_factory=list)
    context_window: Optional[int] = None
    pricing_input_per_1m: Optional[float] = None
    pricing_output_per_1m: Optional[float] = None
    latency_ms: Optional[int] = None
    availability: bool = True
    fallback_models: List[str] = Field(default_factory=list)
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RouterDecision(BaseModel):
    """The router's recommendation for a task (Leader makes the final binding)."""
    task_id: str
    provider: ProviderName
    model_id: str
    base_url: Optional[str] = None
    capabilities: List[ModelCapability] = Field(default_factory=list)
    context_window: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    estimated_latency_ms: Optional[int] = None
    rationale: str = ""
    fallback_chain: List[ModelRegistryEntry] = Field(default_factory=list)
    scored_options: List[Dict[str, Any]] = Field(default_factory=list)
