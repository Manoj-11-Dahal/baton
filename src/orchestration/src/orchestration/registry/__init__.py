"""Central Model Registry.

Maintains provider, model ID, capabilities, modality, pricing, context limits,
availability, latency, and fallback configuration. Provider-independent.
"""
from .registry import ModelRegistry, get_registry, registry_entry_from_db_row

__all__ = ["ModelRegistry", "get_registry", "registry_entry_from_db_row"]
