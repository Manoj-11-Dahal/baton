"""Pytest configuration: shared fixtures for orchestration tests."""
import os
import pytest

# Ensure a clean settings/registry/router/leader for each test session.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://orch_user:orch_pass@localhost:5432/orchestration")


@pytest.fixture
def registry():
    from orchestration.registry.registry import ModelRegistry
    # In-memory only; do NOT hit Postgres in unit tests.
    reg = ModelRegistry(database_url="postgresql+psycopg2://x:x@localhost:1/x")
    reg.seed_defaults()
    return reg


@pytest.fixture
def router(registry):
    from orchestration.router.router import ModelRouter
    return ModelRouter(registry=registry)


@pytest.fixture
def leader(router, registry):
    from orchestration.agents.leader import LeaderAgent
    from orchestration.agents.sub_agents import build_all_sub_agents
    leader = LeaderAgent(router=router, registry=registry)
    for agent in build_all_sub_agents().values():
        leader.register_sub_agent(agent)
    return leader


@pytest.fixture
def engine(leader):
    from orchestration.orchestration.engine import OrchestrationEngine
    return OrchestrationEngine(leader=leader)
