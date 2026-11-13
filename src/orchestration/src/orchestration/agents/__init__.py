"""Leader Agent and specialized Sub-Agents.

The Leader Agent holds EXCLUSIVE authority over all Sub-Agent model selection
and assignment. Sub-Agents cannot independently select, replace, or switch
their assigned models — they must use the ModelAssignment issued by the Leader.
"""
from .base_agent import SubAgent
from .leader import LeaderAgent, get_leader
from .sub_agents import (
    TextSubAgent,
    ImageSubAgent,
    VideoSubAgent,
    AudioSubAgent,
    CodeSubAgent,
    ResearchSubAgent,
    DataSubAgent,
    build_all_sub_agents,
)

__all__ = [
    "LeaderAgent",
    "get_leader",
    "SubAgent",
    "TextSubAgent",
    "ImageSubAgent",
    "VideoSubAgent",
    "AudioSubAgent",
    "CodeSubAgent",
    "ResearchSubAgent",
    "DataSubAgent",
    "build_all_sub_agents",
]
