"""Dynamic Model Router.

Evaluates task type, modality, capability, quality, context window, latency,
availability, cost, and fallback options to recommend a model. The Leader Agent
makes the final binding; the router only advises.
"""
from .router import ModelRouter, get_router

__all__ = ["ModelRouter", "get_router"]
