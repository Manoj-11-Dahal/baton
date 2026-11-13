"""Leader–Sub-Agent Multi-LLM Model Orchestration System.

Production-ready orchestration layer in which the Leader Agent holds exclusive
authority over every Sub-Agent model selection and assignment. Sub-Agents never
select, replace, or switch their own models.

Modules:
    core            — shared types, config, security, observability
    registry        — Central Model Registry (PostgreSQL-backed)
    router          — Dynamic Model Router
    adapters        — Provider adapters (LiteLLM-backed)
    agents          — Leader Agent + specialized Sub-Agents
    orchestration   — LangGraph-based agent communication & orchestration
    quality         — Quality control & fallback system
    api             — FastAPI endpoints & configuration
"""

__version__ = "1.0.0"
