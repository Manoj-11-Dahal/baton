"""FastAPI application exposing orchestration, registry, router, and quality.

Endpoints:
  POST   /orchestrate         - Run full Leader orchestration
  POST   /tasks               - Analyze + create tasks
  POST   /route               - Router recommendation (advisory)
  POST   /assign              - Leader issues a model assignment
  POST   /reassign            - Leader reassigns a model (fallback)
  POST   /execute             - Execute a sub-agent task
  GET    /registry            - List registry models
  GET    /registry/{provider}/{model} - Get a model entry
  POST   /registry/seed       - Seed default registry entries
  GET    /quality/summary     - Quality control summary
  GET    /audit               - Audit log
  GET    /health              - Health check
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..agents.leader import LeaderAgent, get_leader
from ..agents.sub_agents import build_all_sub_agents
from ..core.config import get_settings
from ..core.observability import get_observability
from ..core.types import (
    FallbackReason,
    ModelAssignment,
    Modality,
    ModelRegistryEntry,
    ProviderName,
    QualityReview,
    TaskRequest,
    TaskType,
)
from ..orchestration.engine import get_engine
from ..registry.registry import get_registry
from ..router.router import get_router


app = FastAPI(
    title="Leader–Sub-Agent Multi-LLM Orchestration System",
    version="1.0.0",
    description=(
        "Production-ready orchestration system where the Leader Agent holds "
        "exclusive authority over all Sub-Agent model selection and assignment."
    ),
)

settings = get_settings()


# --------------------------------------------------------------------------- request/response schemas

class OrchestrateRequest(BaseModel):
    user_request: str
    context: Dict[str, Any] = {}
    sequential: bool = False


class RouteRequest(BaseModel):
    task_type: str
    modality: str = "text"
    prompt: str
    required_capabilities: List[str] = []
    preferred_provider: Optional[str] = None
    blocked_providers: List[str] = []
    max_cost_usd: Optional[float] = None
    min_quality_score: Optional[float] = None
    timeout_sec: Optional[int] = None
    max_retries: Optional[int] = None
    context: Dict[str, Any] = {}


class AssignRequest(BaseModel):
    agent_id: str
    task_type: str
    modality: str = "text"
    prompt: str
    required_capabilities: List[str] = []
    context: Dict[str, Any] = {}


class ReassignRequest(BaseModel):
    assignment_id: str
    agent_id: str
    provider: str
    model_id: str
    reason: str = "error"


class ExecuteRequest(BaseModel):
    agent_id: str
    task_type: str
    modality: str = "text"
    prompt: str
    context: Dict[str, Any] = {}


# --------------------------------------------------------------------------- auth (simple bearer token)

def _check_auth(authorization: Optional[str]):
    token = settings.api_auth_token
    if token and token != "change-me-in-production":
        if not authorization or authorization != f"Bearer {token}":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API token.")


# --------------------------------------------------------------------------- eager initialization

def _ensure_initialized():
    """Seed registry and register sub-agents on first use."""
    try:
        get_registry().seed_defaults()
    except Exception:  # noqa: BLE001
        pass
    get_engine()  # registers sub-agents with the shared leader


# Call at import time so tests using TestClient get initialized state.
_ensure_initialized()


# --------------------------------------------------------------------------- endpoints

@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name, "version": "1.0.0"}


@app.post("/orchestrate")
async def orchestrate(req: OrchestrateRequest, authorization: Optional[str] = None):
    _check_auth(authorization)
    engine = get_engine()
    return await engine.run(req.user_request, req.context, req.sequential)


@app.post("/tasks")
async def create_tasks(req: OrchestrateRequest, authorization: Optional[str] = None):
    _check_auth(authorization)
    leader = get_leader()
    tasks = leader.analyze_request(req.user_request, req.context)
    return {"tasks": [t.model_dump() for t in tasks]}


@app.post("/route")
async def route(req: RouteRequest, authorization: Optional[str] = None):
    _check_auth(authorization)
    router = get_router()
    task = TaskRequest(
        task_type=TaskType(req.task_type),
        modality=Modality(req.modality),
        prompt=req.prompt,
        required_capabilities=[ModelCapabilityFromStr(c) for c in req.required_capabilities],
        preferred_provider=ProviderName(req.preferred_provider) if req.preferred_provider else None,
        blocked_providers=[ProviderName(p) for p in req.blocked_providers],
        max_cost_usd=req.max_cost_usd,
        min_quality_score=req.min_quality_score,
        timeout_sec=req.timeout_sec,
        max_retries=req.max_retries,
        context=req.context,
    )
    decision = router.route(task)
    return decision.model_dump()


@app.post("/assign", response_model=Dict[str, Any])
async def assign(req: AssignRequest, authorization: Optional[str] = None):
    _check_auth(authorization)
    leader = get_leader()
    task = TaskRequest(
        task_type=TaskType(req.task_type),
        modality=Modality(req.modality),
        prompt=req.prompt,
        required_capabilities=[ModelCapabilityFromStr(c) for c in req.required_capabilities],
        context=req.context,
    )
    assignment = leader.assign_model(req.agent_id, task)
    return assignment.model_dump()


@app.post("/reassign")
async def reassign(req: ReassignRequest, authorization: Optional[str] = None):
    _check_auth(authorization)
    leader = get_leader()
    try:
        reason = FallbackReason(req.reason)
    except ValueError:
        reason = FallbackReason.ERROR
    assignment = leader.reassign_model(
        req.assignment_id, req.agent_id, ProviderName(req.provider), req.model_id, reason
    )
    return assignment.model_dump()


@app.post("/execute")
async def execute(req: ExecuteRequest, authorization: Optional[str] = None):
    _check_auth(authorization)
    leader = get_leader()
    task = TaskRequest(
        task_type=TaskType(req.task_type),
        modality=Modality(req.modality),
        prompt=req.prompt,
        context=req.context,
    )
    result = await leader.execute_sub_agent(req.agent_id, task)
    return result.model_dump()


@app.get("/registry")
async def list_registry(
    provider: Optional[str] = Query(None),
    capability: Optional[str] = Query(None),
    modality: Optional[str] = Query(None),
    authorization: Optional[str] = None,
):
    _check_auth(authorization)
    registry = get_registry()
    p = ProviderName(provider) if provider else None
    cap = ModelCapabilityFromStr(capability) if capability else None
    mod = Modality(modality) if modality else None
    models = registry.list_models(provider=p, capability=cap, modality=mod)
    return {"models": [m.model_dump() for m in models]}


@app.get("/registry/{provider}/{model_id:path}")
async def get_registry_model(provider: str, model_id: str, authorization: Optional[str] = None):
    _check_auth(authorization)
    registry = get_registry()
    entry = registry.get(ProviderName(provider), model_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Model not found in registry.")
    return entry.model_dump()


@app.post("/registry/seed")
async def seed_registry(authorization: Optional[str] = None):
    _check_auth(authorization)
    registry = get_registry()
    registry.seed_defaults()
    return {"status": "seeded"}


@app.get("/quality/summary")
async def quality_summary(authorization: Optional[str] = None):
    _check_auth(authorization)
    from ..quality.quality import get_quality_controller

    return get_quality_controller().summarize()


@app.get("/audit")
async def audit(authorization: Optional[str] = None):
    _check_auth(authorization)
    leader = get_leader()
    return {"audit": leader.security.get_audit_log()}


@app.get("/agents")
async def list_agents(authorization: Optional[str] = None):
    _check_auth(authorization)
    leader = get_leader()
    return {
        "leader": {"id": leader.agent_id, "name": leader.name},
        "sub_agents": [
            {
                "id": a.agent_id,
                "name": a.name,
                "task_type": a.task_type,
                "description": a.description,
                "has_assignment": a.assignment is not None,
                "assigned_model": a.assignment.model_id if a.assignment else None,
                "assigned_provider": a.assignment.provider.value if a.assignment else None,
            }
            for a in leader.sub_agents.values()
        ],
    }


# --------------------------------------------------------------------------- helper

def ModelCapabilityFromStr(value: str):
    from ..core.types import ModelCapability

    try:
        return ModelCapability(value)
    except ValueError:
        return ModelCapability.TEXT_GENERATION


@app.on_event("startup")
async def _startup():
    # Ensure registry has default entries and sub-agents are registered.
    try:
        get_registry().seed_defaults()
    except Exception:  # noqa: BLE001
        # DB may not be available in dev; that's OK.
        pass
    get_engine()  # registers sub-agents
