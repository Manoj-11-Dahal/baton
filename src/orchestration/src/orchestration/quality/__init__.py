"""Quality control and fallback system.

The Leader Agent reviews all results, resolves conflicts, and applies model
fallback when quality is below threshold or a model errors. Sub-Agents do not
participate in quality decisions beyond producing results.
"""
from .quality import QualityController, get_quality_controller

__all__ = ["QualityController", "get_quality_controller"]
