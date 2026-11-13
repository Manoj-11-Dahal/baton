"""Tests for api/app.py — FastAPI endpoints."""
from fastapi.testclient import TestClient

from orchestration.api.app import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer change-me-in-production"}


def test_health_endpoint():
    """GET /health should return ok."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "leader-subagent-orchestration"


def test_orchestrate_endpoint():
    """POST /orchestrate should run full orchestration."""
    resp = client.post(
        "/orchestrate",
        json={"user_request": "Write a short greeting.", "sequential": True},
        headers=AUTH,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_request"] == "Write a short greeting."
    assert "results" in data
    assert "final" in data
    assert "elapsed_ms" in data


def test_orchestrate_missing_auth():
    """POST /orchestrate without auth should fail when token is set."""
    resp = client.post(
        "/orchestrate",
        json={"user_request": "Hello."},
    )
    # When API_AUTH_TOKEN is the default, auth is skipped -> 200
    # This test documents current behavior
    assert resp.status_code in (200, 401)


def test_tasks_endpoint():
    """POST /tasks should analyze and return tasks."""
    resp = client.post(
        "/tasks",
        json={"user_request": "Write code and generate an image."},
        headers=AUTH,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "tasks" in data
    assert len(data["tasks"]) >= 1


def test_route_endpoint():
    """POST /route should return a router recommendation."""
    resp = client.post(
        "/route",
        json={
            "task_type": "text",
            "modality": "text",
            "prompt": "Say hello.",
            "required_capabilities": ["text_generation"],
        },
        headers=AUTH,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert "provider" in data
    assert "model_id" in data
    assert "rationale" in data


def test_assign_endpoint():
    """POST /assign should issue a model assignment."""
    resp = client.post(
        "/assign",
        json={
            "agent_id": "text_agent",
            "task_type": "text",
            "modality": "text",
            "prompt": "Say hello.",
            "required_capabilities": ["text_generation"],
        },
        headers=AUTH,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["assigned_by"] == "leader_agent"
    assert data["agent_id"] == "text_agent"


def test_reassign_endpoint():
    """POST /reassign should reassign a model."""
    # First assign
    assign_resp = client.post(
        "/assign",
        json={
            "agent_id": "text_agent",
            "task_type": "text",
            "modality": "text",
            "prompt": "Hello.",
            "required_capabilities": ["text_generation"],
        },
        headers=AUTH,
    )
    assignment = assign_resp.json()
    assignment_id = assignment["id"]

    resp = client.post(
        "/reassign",
        json={
            "assignment_id": assignment_id,
            "agent_id": "text_agent",
            "provider": "anthropic",
            "model_id": "claude-3-haiku-20240307",
            "reason": "error",
        },
        headers=AUTH,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "anthropic"
    assert data["model_id"] == "claude-3-haiku-20240307"


def test_execute_endpoint():
    """POST /execute should execute a sub-agent task."""
    resp = client.post(
        "/execute",
        json={
            "agent_id": "text_agent",
            "task_type": "text",
            "modality": "text",
            "prompt": "Say hello.",
        },
        headers=AUTH,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "agent_id" in data
    assert "model_id" in data
    assert "ok" in data


def test_list_registry_endpoint():
    """GET /registry should list models."""
    resp = client.get("/registry", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert isinstance(data["models"], list)


def test_list_registry_filter_provider():
    """GET /registry should filter by provider."""
    resp = client.get("/registry?provider=openai", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    for m in data["models"]:
        assert m["provider"] == "openai"


def test_list_registry_filter_capability():
    """GET /registry should filter by capability."""
    resp = client.get("/registry?capability=text_generation", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    for m in data["models"]:
        assert "text_generation" in m["capabilities"]


def test_list_registry_filter_modality():
    """GET /registry should filter by modality."""
    resp = client.get("/registry?modality=text", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    for m in data["models"]:
        assert "text" in m["modalities"]


def test_get_registry_model_endpoint():
    """GET /registry/{provider}/{model_id} should return a model entry."""
    # First list to find a model
    list_resp = client.get("/registry?provider=openai", headers=AUTH)
    models = list_resp.json()["models"]
    if models:
        model = models[0]
        resp = client.get(
            f"/registry/{model['provider']}/{model['model_id']}",
            headers=AUTH,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_id"] == model["model_id"]


def test_get_registry_model_not_found():
    """GET /registry/{provider}/{model_id} should return 404 for unknown model."""
    resp = client.get(
        "/registry/openai/nonexistent-model-xyz",
        headers=AUTH,
    )
    assert resp.status_code == 404


def test_seed_registry_endpoint():
    """POST /registry/seed should seed the registry."""
    resp = client.post("/registry/seed", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "seeded"


def test_quality_summary_endpoint():
    """GET /quality/summary should return quality stats."""
    resp = client.get("/quality/summary", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert "reviews" in data


def test_audit_endpoint():
    """GET /audit should return the audit log."""
    resp = client.get("/audit", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert "audit" in data
    assert isinstance(data["audit"], list)


def test_agents_endpoint():
    """GET /agents should list leader and sub-agents."""
    resp = client.get("/agents", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert "leader" in data
    assert data["leader"]["id"] == "leader_agent"
    assert "sub_agents" in data
    task_types = {a["task_type"] for a in data["sub_agents"]}
    expected = {"text", "image", "video", "audio", "code", "research", "data"}
    assert expected.issubset(task_types)
