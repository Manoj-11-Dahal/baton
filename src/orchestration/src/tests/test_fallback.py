"""Tests for quality control and model fallback (Leader-driven)."""
from orchestration.core.types import (
    FallbackReason,
    Modality,
    ModelCapability,
    ModelRegistryEntry,
    ProviderName,
    TaskRequest,
    TaskType,
)
from orchestration.agents.leader import LeaderAgent
from orchestration.router.router import ModelRouter
from orchestration.registry.registry import ModelRegistry


def _reg():
    reg = ModelRegistry(database_url="postgresql+psycopg2://x:x@localhost:1/x")
    openai = ModelRegistryEntry(
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        capabilities=[ModelCapability.TEXT_GENERATION],
        modalities=[Modality.TEXT], latency_ms=1000, pricing_output_per_1m=2.5,
        context_window=128000, availability=True, fallback_models=["gpt-4o-mini"],
    )
    mini = ModelRegistryEntry(
        provider=ProviderName.OPENAI, model_id="gpt-4o-mini",
        capabilities=[ModelCapability.TEXT_GENERATION],
        modalities=[Modality.TEXT], latency_ms=600, pricing_output_per_1m=0.15,
        context_window=128000, availability=True, fallback_models=[],
    )
    reg._cache = {"openai:gpt-4o": openai, "openai:gpt-4o-mini": mini}
    reg._cache_loaded_at = 0
    return reg


def test_router_recommends_fallback_on_error(router=None):
    reg = _reg()
    router = ModelRouter(registry=reg)
    task = TaskRequest(
        task_type=TaskType.TEXT,
        modality=Modality.TEXT,
        prompt="Hello.",
        required_capabilities=[ModelCapability.TEXT_GENERATION],
    )
    # Current assignment gpt-4o fails; router recommends fallback.
    from orchestration.core.types import ModelAssignment
    current = ModelAssignment(
        task_id="t1", agent_id="text_agent",
        provider=ProviderName.OPENAI, model_id="gpt-4o",
        assigned_by="leader_agent", active=True,
        fallback_assignments=[
            ModelAssignment(
                task_id="t1", agent_id="text_agent",
                provider=ProviderName.OPENAI, model_id="gpt-4o-mini",
                assigned_by="leader_agent", active=False,
            )
        ],
    )
    fb = router.recommend_fallback(current, FallbackReason.ERROR, task)
    assert fb is not None
    assert fb.model_id == "gpt-4o-mini"


def test_quality_controller_summary():
    from orchestration.quality.quality import QualityController
    qc = QualityController()
    assert qc.summarize()["reviews"] == 0
