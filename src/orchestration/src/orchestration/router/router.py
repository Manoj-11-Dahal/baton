"""Dynamic Model Router.

Scores candidate models for a task and produces a recommendation plus a ranked
fallback chain. The Leader Agent holds exclusive authority over the final model
assignment — the router only advises and cannot assign models itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..core.config import get_settings
from ..core.observability import get_observability
from ..core.types import (
    FallbackReason,
    Modality,
    ModelCapability,
    ModelRegistryEntry,
    ModelAssignment,
    ProviderName,
    RouterDecision,
    TaskRequest,
)
from ..registry.registry import ModelRegistry, get_registry


# Task type -> primary capability mapping
TASK_CAPABILITY: Dict[str, ModelCapability] = {
    "text": ModelCapability.TEXT_GENERATION,
    "code": ModelCapability.CODE_GENERATION,
    "image": ModelCapability.IMAGE_GENERATION,
    "video": ModelCapability.VIDEO_GENERATION,
    "audio": ModelCapability.AUDIO_GENERATION,
    "research": ModelCapability.TEXT_GENERATION,
    "data": ModelCapability.TEXT_GENERATION,
}

# Modality -> required capability hints
MODALITY_CAPABILITIES: Dict[str, List[ModelCapability]] = {
    "text": [ModelCapability.TEXT_GENERATION],
    "image": [ModelCapability.IMAGE_GENERATION, ModelCapability.MULTIMODAL_INPUT],
    "video": [ModelCapability.VIDEO_GENERATION],
    "audio": [ModelCapability.AUDIO_GENERATION, ModelCapability.SPEECH_TO_TEXT, ModelCapability.TEXT_TO_SPEECH],
    "code": [ModelCapability.CODE_GENERATION],
    "embedding": [ModelCapability.EMBEDDINGS],
    "multimodal": [ModelCapability.MULTIMODAL_INPUT],
    "speech": [ModelCapability.SPEECH_TO_TEXT, ModelCapability.TEXT_TO_SPEECH],
}


@dataclass
class _Score:
    entry: ModelRegistryEntry
    score: float
    rationale: List[str] = field(default_factory=list)


class ModelRouter:
    """Recommend a model (and fallback chain) for a given task.

    The router is purely advisory. It never assigns models to agents. The
    Leader Agent makes the final binding and records it as a ModelAssignment.
    """

    def __init__(self, registry: Optional[ModelRegistry] = None):
        settings = get_settings()
        self.registry = registry or get_registry()
        self.settings = settings
        self.obs = get_observability()

    # ---------------------------------------------------------------- routing

    def route(self, task: TaskRequest) -> RouterDecision:
        """Route a task to a recommended model with fallback chain.

        Evaluation factors:
          - capability match (required capabilities must be present)
          - modality support
          - context window vs estimated context need
          - quality (provider/reputation proxy)
          - latency
          - availability
          - cost (vs max_cost_usd)
          - fallback options
        """
        with self.obs.span("router.route", attributes={"task_id": task.id, "task_type": task.task_type}) as span:
            candidates = self._candidates(task)
            if not candidates:
                # No capable model — report unsupported capability clearly.
                decision = RouterDecision(
                    task_id=task.id,
                    provider=ProviderName.LOCAL,
                    model_id="unsupported",
                    rationale=(
                        f"No available model supports task_type={task.task_type}, "
                        f"modality={task.modality}, capabilities="
                        f"{[c.value for c in task.required_capabilities]}. "
                        "Add a provider/model with the needed capability or enable a local model."
                    ),
                    scored_options=[],
                )
                self.obs.record_quality(task.id, 0.0, False)
                return decision

            scored = [self._score(entry, task) for entry in candidates]
            scored.sort(key=lambda s: s.score, reverse=True)
            best = scored[0]

            # Build fallback chain from the best model's configured fallbacks,
            # then other capable models ranked by score.
            fallback_chain = self._build_fallback_chain(best.entry, task, scored)

            decision = RouterDecision(
                task_id=task.id,
                provider=best.entry.provider,
                model_id=best.entry.model_id,
                base_url=best.entry.base_url,
                capabilities=best.entry.capabilities,
                context_window=best.entry.context_window,
                estimated_cost_usd=self._estimate_cost(best.entry, task),
                estimated_latency_ms=best.entry.latency_ms,
                rationale="; ".join(best.rationale),
                fallback_chain=fallback_chain,
                scored_options=[
                    {
                        "provider": s.entry.provider.value,
                        "model_id": s.entry.model_id,
                        "score": round(s.score, 3),
                        "rationale": "; ".join(s.rationale),
                    }
                    for s in scored[:5]
                ],
            )

            span.attributes.update(
                {
                    "selected_provider": decision.provider.value,
                    "selected_model": decision.model_id,
                    "score": best.score,
                    "candidates": len(candidates),
                }
            )
            return decision

    def route_to_assignment(
        self, task: TaskRequest, agent_id: str, assigned_by: str = "leader_agent"
    ) -> ModelAssignment:
        """Convenience: route and produce a Leader ModelAssignment.

        This is how the Leader Agent obtains a binding. The assignment is the
        authoritative record a sub-agent must follow.
        """
        decision = self.route(task)
        if decision.model_id == "unsupported":
            raise ValueError(decision.rationale)

        fallback_assignments = [
            ModelAssignment(
                task_id=task.id,
                agent_id=agent_id,
                provider=fb.provider,
                model_id=fb.model_id,
                base_url=fb.base_url,
                api_key_env=fb.api_key_env,
                capabilities=fb.capabilities,
                context_window=fb.context_window,
                max_retries=task.max_retries or self.settings.default_max_retries,
                timeout_sec=task.timeout_sec or self.settings.default_request_timeout_sec,
                assigned_by=assigned_by,
                active=False,  # fallbacks are inactive until promoted by Leader
            )
            for fb in decision.fallback_chain[:3]
        ]

        entry = self.registry.get(decision.provider, decision.model_id)
        return ModelAssignment(
            task_id=task.id,
            agent_id=agent_id,
            provider=decision.provider,
            model_id=decision.model_id,
            base_url=decision.base_url or (entry.base_url if entry else None),
            api_key_env=(entry.api_key_env if entry else None),
            capabilities=decision.capabilities,
            context_window=decision.context_window,
            estimated_cost_usd=decision.estimated_cost_usd,
            timeout_sec=task.timeout_sec or self.settings.default_request_timeout_sec,
            max_retries=task.max_retries or self.settings.default_max_retries,
            fallback_assignments=fallback_assignments,
            assigned_by=assigned_by,
            active=True,
        )

    # ---------------------------------------------------------------- internals

    def _candidates(self, task: TaskRequest) -> List[ModelRegistryEntry]:
        """Filter registry to models capable of the task."""
        # Determine required capability from task type / explicit capabilities.
        required = list(task.required_capabilities)
        primary = TASK_CAPABILITY.get(task.task_type.value)
        if primary and primary not in required:
            required.append(primary)

        # Modality filter: model must support the task's modality.
        modality = task.modality

        # Gather all models matching at least one required capability.
        seen: Dict[str, ModelRegistryEntry] = {}
        for cap in required:
            for entry in self.registry.get_capable_models(cap, modality=modality):
                if entry.enabled and entry.availability:
                    seen[f"{entry.provider.value}:{entry.model_id}"] = entry

        # If no modality-specific match and modality is multimodal, also accept
        # text-capable models (they can still process the text portion).
        if not seen and modality == Modality.MULTIMODAL:
            for cap in required:
                for entry in self.registry.get_capable_models(cap):
                    if entry.enabled and entry.availability and Modality.TEXT in entry.modalities:
                        seen[f"{entry.provider.value}:{entry.model_id}"] = entry

        # Apply provider preferences / blocks.
        results: List[ModelRegistryEntry] = []
        for entry in seen.values():
            if task.preferred_provider and entry.provider != task.preferred_provider:
                continue
            if entry.provider in task.blocked_providers:
                continue
            # Cost ceiling
            if task.max_cost_usd is not None and entry.pricing_output_per_1m is not None:
                if entry.pricing_output_per_1m > task.max_cost_usd:
                    continue
            results.append(entry)
        return results

    def _score(self, entry: ModelRegistryEntry, task: TaskRequest) -> _Score:
        score = 0.0
        rationale: List[str] = []

        # Capability match (must-have): already filtered, so all candidates pass.
        rationale.append(f"supports {task.task_type.value}")

        # Modality support bonus
        if task.modality in entry.modalities:
            score += 30.0
            rationale.append(f"modality {task.modality.value}")
        else:
            score += 5.0  # partial (e.g. text-only for multimodal task)
            rationale.append(f"partial modality {task.modality.value}")

        # Context window fit
        if entry.context_window:
            if entry.context_window >= 128000:
                score += 15.0
                rationale.append("long context")
            elif entry.context_window >= 32000:
                score += 8.0
            rationale.append(f"ctx={entry.context_window}")
        else:
            score += 5.0

        # Quality proxy: reasoning/capability breadth
        cap_bonus = len(entry.capabilities) * 2.0
        score += min(cap_bonus, 10.0)
        if ModelCapability.REASONING in entry.capabilities:
            score += 8.0
            rationale.append("reasoning")

        # Latency (lower is better)
        if entry.latency_ms:
            if entry.latency_ms <= 600:
                score += 10.0
            elif entry.latency_ms <= 1500:
                score += 5.0
            rationale.append(f"latency~{entry.latency_ms}ms")

        # Availability
        if entry.availability:
            score += 10.0
        else:
            score -= 20.0

        # Cost (lower is better, but prefer capability over cheapest)
        if entry.pricing_output_per_1m is not None:
            if entry.pricing_output_per_1m <= 1.0:
                score += 8.0
                rationale.append("low cost")
            elif entry.pricing_output_per_1m <= 5.0:
                score += 4.0
            else:
                score += 1.0
        else:
            # local/free models
            score += 10.0
            rationale.append("local/free")

        # Preferred provider bonus
        if task.preferred_provider and entry.provider == task.preferred_provider:
            score += 10.0
            rationale.append("preferred provider")

        return _Score(entry=entry, score=round(score, 2), rationale=rationale)

    def _estimate_cost(self, entry: ModelRegistryEntry, task: TaskRequest) -> Optional[float]:
        if not entry.pricing_output_per_1m:
            return None
        # Rough estimate: prompt tokens + output tokens. Use context budget as proxy.
        est_tokens = max(len(task.prompt) // 4, 100) + 500
        return round((est_tokens / 1_000_000) * entry.pricing_output_per_1m, 6)

    def _build_fallback_chain(
        self, best: ModelRegistryEntry, task: TaskRequest, scored: List[_Score]
    ) -> List[ModelRegistryEntry]:
        chain: List[ModelRegistryEntry] = []
        seen: set = set()

        # 1) Configured fallbacks of the best model (same provider).
        for fid in best.fallback_models:
            fb = self.registry.get(best.provider, fid)
            if fb and fb.enabled and fb.availability and fb.model_id != best.model_id:
                chain.append(fb)
                seen.add(f"{fb.provider}:{fb.model_id}")

        # 2) Other capable models ranked by score (different provider preferred).
        for s in scored:
            key = f"{s.entry.provider}:{s.entry.model_id}"
            if key in seen:
                continue
            if s.entry.model_id == best.model_id:
                continue
            chain.append(s.entry)
            seen.add(key)
            if len(chain) >= 4:
                break

        return chain

    def recommend_fallback(
        self, current: ModelAssignment, reason: FallbackReason, task: TaskRequest
    ) -> Optional[ModelAssignment]:
        """Recommend a fallback assignment when the current model fails.

        The Leader Agent decides whether to adopt the recommendation.
        """
        # Try configured fallback assignments first.
        for fb in current.fallback_assignments:
            if fb.active:
                continue
            entry = self.registry.get(fb.provider, fb.model_id)
            if entry and entry.enabled and entry.availability:
                fb.active = True
                return fb

        # Otherwise route the task again excluding the failed provider/model.
        blocked = list(task.blocked_providers)
        if current.provider not in blocked:
            blocked.append(current.provider)
        task2 = TaskRequest(
            id=task.id,
            task_type=task.task_type,
            modality=task.modality,
            prompt=task.prompt,
            context=task.context,
            required_capabilities=task.required_capabilities,
            preferred_provider=task.preferred_provider,
            blocked_providers=blocked,
            max_cost_usd=task.max_cost_usd,
            min_quality_score=task.min_quality_score,
            timeout_sec=task.timeout_sec,
            max_retries=task.max_retries,
            metadata={**task.metadata, "fallback_reason": reason.value},
        )
        try:
            return self.route_to_assignment(task2, current.agent_id, assigned_by="leader_agent")
        except ValueError:
            return None


_router: Optional[ModelRouter] = None


def get_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router
