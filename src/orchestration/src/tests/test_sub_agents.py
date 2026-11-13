"""Tests for agents/sub_agents.py — all 7 specialized Sub-Agents."""
import asyncio

import pytest

from orchestration.adapters.base import ModelCall, ModelResponse, register_adapter
from orchestration.agents.sub_agents import (
    AudioSubAgent,
    CodeSubAgent,
    DataSubAgent,
    ImageSubAgent,
    ResearchSubAgent,
    TextSubAgent,
    VideoSubAgent,
    build_all_sub_agents,
)
from orchestration.core.types import (
    Modality,
    ProviderName,
    TaskRequest,
    TaskType,
)


class RecordingAdapter:
    def __init__(self, responses=None, fail_on=None):
        self.responses = responses or {}
        self.fail_on = fail_on or set()
        self.calls = []

    async def call(self, call: ModelCall) -> ModelResponse:
        self.calls.append(call)
        if call.model_id in self.fail_on:
            return ModelResponse(
                model_id=call.model_id,
                provider=call.provider,
                content="",
                ok=False,
                error="simulated error",
            )
        return ModelResponse(
            model_id=call.model_id,
            provider=call.provider,
            content=self.responses.get(call.model_id, "stub response"),
            ok=True,
            usage={"input": 10, "output": 5},
            latency_ms=100,
            cost_usd=0.001,
        )


def test_text_sub_agent():
    agent = TextSubAgent()
    assert agent.agent_id == "text_agent"
    assert agent.name == "Text Sub-Agent"
    assert agent.task_type == "text"
    assert "text" in agent.description.lower()
    assert agent.assignment is None


def test_image_sub_agent():
    agent = ImageSubAgent()
    assert agent.agent_id == "image_agent"
    assert agent.name == "Image Sub-Agent"
    assert agent.task_type == "image"
    assert agent.assignment is None


def test_video_sub_agent():
    agent = VideoSubAgent()
    assert agent.agent_id == "video_agent"
    assert agent.name == "Video Sub-Agent"
    assert agent.task_type == "video"
    assert agent.assignment is None


def test_audio_sub_agent():
    agent = AudioSubAgent()
    assert agent.agent_id == "audio_agent"
    assert agent.name == "Audio Sub-Agent"
    assert agent.task_type == "audio"
    assert agent.assignment is None


def test_code_sub_agent():
    agent = CodeSubAgent()
    assert agent.agent_id == "code_agent"
    assert agent.name == "Code Sub-Agent"
    assert agent.task_type == "code"
    assert agent.assignment is None


def test_research_sub_agent():
    agent = ResearchSubAgent()
    assert agent.agent_id == "research_agent"
    assert agent.name == "Research Sub-Agent"
    assert agent.task_type == "research"
    assert agent.assignment is None


def test_data_sub_agent():
    agent = DataSubAgent()
    assert agent.agent_id == "data_agent"
    assert agent.name == "Data Sub-Agent"
    assert agent.task_type == "data"
    assert agent.assignment is None


def test_build_all_sub_agents():
    agents = build_all_sub_agents()
    assert isinstance(agents, dict)
    assert set(agents.keys()) == {
        "text", "image", "video", "audio", "code", "research", "data",
    }
    assert isinstance(agents["text"], TextSubAgent)
    assert isinstance(agents["image"], ImageSubAgent)
    assert isinstance(agents["video"], VideoSubAgent)
    assert isinstance(agents["audio"], AudioSubAgent)
    assert isinstance(agents["code"], CodeSubAgent)
    assert isinstance(agents["research"], ResearchSubAgent)
    assert isinstance(agents["data"], DataSubAgent)


def test_sub_agent_rejects_model_switch():
    """Each sub-agent must reject attempts to switch its assigned model."""
    for agent in build_all_sub_agents().values():
        from orchestration.core.types import ModelAssignment
        a = ModelAssignment(
            task_id="t1", agent_id=agent.agent_id,
            provider=ProviderName.OPENAI, model_id="gpt-4o",
            assigned_by="leader_agent",
        )
        agent.set_assignment(a, issued_by="leader_agent")
        with pytest.raises(PermissionError):
            agent._enforce_model_authority(ProviderName.ANTHROPIC, "claude-3-haiku-20240307")
        # Assignment unchanged
        assert agent.assignment.model_id == "gpt-4o"
        assert agent.assignment.provider == ProviderName.OPENAI


@pytest.mark.asyncio
async def test_each_sub_agent_executes_with_assigned_model(monkeypatch):
    """Each sub-agent should execute using the leader-assigned model."""
    agents = build_all_sub_agents()
    model_map = {
        "text": ("openai", "gpt-4o-text", "text result"),
        "image": ("openai", "dall-e-3", "image result"),
        "video": ("openai", "sora", "video result"),
        "audio": ("openai", "tts-1", "audio result"),
        "code": ("openai", "gpt-4o-code", "code result"),
        "research": ("anthropic", "claude-3-haiku-20240307", "research result"),
        "data": ("openai", "gpt-4o-data", "data result"),
    }

    # Build one RecordingAdapter per provider, keyed by model_id.
    provider_recs = {}
    for key, (prov, model, content) in model_map.items():
        if prov not in provider_recs:
            provider_recs[prov] = RecordingAdapter()
        provider_recs[prov].responses[model] = content
        register_adapter(prov, provider_recs[prov])

    try:
        import orchestration.agents.base_agent as base_mod
        orig_get = base_mod.get_adapter

        def fake_get(name):
            if name in provider_recs:
                return provider_recs[name]
            return orig_get(name)

        monkeypatch.setattr(base_mod, "get_adapter", fake_get)

        for key, agent in agents.items():
            prov, model, content = model_map[key]
            from orchestration.core.types import ModelAssignment
            a = ModelAssignment(
                task_id="t1", agent_id=agent.agent_id,
                provider=ProviderName(prov), model_id=model,
                assigned_by="leader_agent",
            )
            agent.set_assignment(a, issued_by="leader_agent")

            task = TaskRequest(
                task_type=TaskType(key),
                modality=Modality.TEXT,
                prompt="Do the task.",
            )
            result = await agent.execute(task)

            assert result.ok is True, f"{key} agent failed: {result.error}"
            assert result.content == content
            assert result.model_id == model
            assert result.provider == ProviderName(prov)
            assert len(provider_recs[prov].calls) >= 1
            assert provider_recs[prov].calls[-1].model_id == model
    finally:
        from orchestration.adapters.base import _ADAPTERS
        for prov in {"openai", "anthropic"}:
            _ADAPTERS.pop(prov, None)
