"""Specialized Sub-Agents.

Each sub-agent executes tasks using ONLY the model assigned by the Leader Agent.
They cannot select, replace, or switch their own models. The Leader Agent binds
each one to a provider/model via a ModelAssignment before execution.

Supported sub-agents:
  - TextSubAgent      : text generation, summarization, writing
  - ImageSubAgent     : image generation
  - VideoSubAgent     : video generation (specialized APIs when LLM insufficient)
  - AudioSubAgent     : audio / speech generation and transcription
  - CodeSubAgent      : code generation, debugging, review
  - ResearchSubAgent  : research, web search, source synthesis
  - DataSubAgent      : data analysis, queries, transformations
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..core.types import Modality, TaskRequest, TaskType
from .base_agent import SubAgent


class TextSubAgent(SubAgent):
    def __init__(self, agent_id: str = "text_agent"):
        super().__init__(
            agent_id=agent_id,
            name="Text Sub-Agent",
            description="Text generation, summarization, and general writing tasks.",
            task_type="text",
            system_prompt=(
                "You are the Text Sub-Agent. You handle text generation, "
                "summarization, writing, and general language tasks. "
                "Use only the model assigned to you by the Leader Agent. "
                "Produce clear, well-structured, accurate text output."
            ),
        )


class ImageSubAgent(SubAgent):
    def __init__(self, agent_id: str = "image_agent"):
        super().__init__(
            agent_id=agent_id,
            name="Image Sub-Agent",
            description="Image generation using specialized image generation APIs.",
            task_type="image",
            system_prompt=(
                "You are the Image Sub-Agent. You generate or describe images. "
                "When a conventional LLM endpoint is insufficient, use the "
                "specialized image generation API (e.g. DALL-E 3, Imagen) bound "
                "to you by the Leader Agent. You cannot choose your own model. "
                "Return image descriptions, URLs, or generation results."
            ),
        )


class VideoSubAgent(SubAgent):
    def __init__(self, agent_id: str = "video_agent"):
        super().__init__(
            agent_id=agent_id,
            name="Video Sub-Agent",
            description="Video generation using specialized video generation APIs.",
            task_type="video",
            system_prompt=(
                "You are the Video Sub-Agent. You handle video generation tasks. "
                "Conventional LLM endpoints cannot generate video directly; use the "
                "specialized video generation API bound to you by the Leader Agent. "
                "You cannot choose or switch your own model. "
                "Return video generation results, URLs, or a plan for production."
            ),
        )


class AudioSubAgent(SubAgent):
    def __init__(self, agent_id: str = "audio_agent"):
        super().__init__(
            agent_id=agent_id,
            name="Audio Sub-Agent",
            description="Audio generation, speech-to-text, and text-to-speech.",
            task_type="audio",
            system_prompt=(
                "You are the Audio Sub-Agent. You handle audio generation, "
                "transcription (speech-to-text), and text-to-speech tasks. "
                "Use specialized audio APIs when a conventional LLM endpoint is "
                "insufficient. You cannot choose your own model; the Leader Agent "
                "assigns it. Return audio results, transcripts, or generation outputs."
            ),
        )


class CodeSubAgent(SubAgent):
    def __init__(self, agent_id: str = "code_agent"):
        super().__init__(
            agent_id=agent_id,
            name="Code Sub-Agent",
            description="Code generation, debugging, and code review.",
            task_type="code",
            system_prompt=(
                "You are the Code Sub-Agent. You handle code generation, debugging, "
                "review, and implementation tasks. Use the model assigned by the "
                "Leader Agent. Produce clean, well-commented, working code and "
                "explain your approach. You cannot choose or switch your model."
            ),
        )


class ResearchSubAgent(SubAgent):
    def __init__(self, agent_id: str = "research_agent"):
        super().__init__(
            agent_id=agent_id,
            name="Research Sub-Agent",
            description="Research, web search, and source synthesis.",
            task_type="research",
            system_prompt=(
                "You are the Research Sub-Agent. You conduct research, locate and "
                "evaluate sources, and synthesize findings into a structured report. "
                "Use the model assigned by the Leader Agent. Cite sources where "
                "possible. You cannot choose or switch your model."
            ),
        )


class DataSubAgent(SubAgent):
    def __init__(self, agent_id: str = "data_agent"):
        super().__init__(
            agent_id=agent_id,
            name="Data Sub-Agent",
            description="Data analysis, queries, and transformations.",
            task_type="data",
            system_prompt=(
                "You are the Data Sub-Agent. You handle data analysis, database "
                "queries, data transformation, and insight extraction. Use the "
                "model assigned by the Leader Agent. You may use sandboxed code "
                "execution only if the Leader Agent permits it. You cannot choose "
                "or switch your model."
            ),
        )


def build_all_sub_agents() -> Dict[str, SubAgent]:
    """Build all seven specialized sub-agents."""
    return {
        "text": TextSubAgent(),
        "image": ImageSubAgent(),
        "video": VideoSubAgent(),
        "audio": AudioSubAgent(),
        "code": CodeSubAgent(),
        "research": ResearchSubAgent(),
        "data": DataSubAgent(),
    }


# Convenience instances.
text_agent = TextSubAgent()
image_agent = ImageSubAgent()
video_agent = VideoSubAgent()
audio_agent = AudioSubAgent()
code_agent = CodeSubAgent()
research_agent = ResearchSubAgent()
data_agent = DataSubAgent()

__all__ = [
    "TextSubAgent",
    "ImageSubAgent",
    "VideoSubAgent",
    "AudioSubAgent",
    "CodeSubAgent",
    "ResearchSubAgent",
    "DataSubAgent",
    "build_all_sub_agents",
    "text_agent",
    "image_agent",
    "video_agent",
    "audio_agent",
    "code_agent",
    "research_agent",
    "data_agent",
]
