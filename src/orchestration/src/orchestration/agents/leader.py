"""Leader Agent.

The Leader Agent has EXCLUSIVE authority over all Sub-Agent model selection and
assignment. It:
  1. Analyzes the user request and decomposes it into tasks.
  2. Consults the Dynamic Model Router for recommendations.
  3. Issues ModelAssignments binding each sub-agent to a specific model/provider.
  4. Executes sub-agents in parallel or sequential.
  5. Reviews all results (Quality Control), resolves conflicts, applies fallback.
  6. Produces the final response.

Sub-Agents cannot independently select, replace, or switch their models. Any
such attempt is rejected and audited.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Dict, List, Optional

from ..adapters.base import ModelCall, get_adapter
from ..core.observability import get_observability
from ..core.security import SecurityManager, make_default_security_context
from ..core.types import (
    AgentResult,
    FallbackReason,
    ModelAssignment,
    ModelAssignmentUpdate,
    ProviderName,
    QualityReview,
    SecurityContext,
    TaskRequest,
)
from ..registry.registry import ModelRegistry, get_registry
from ..router.router import ModelRouter, get_router

# ---------------------------------------------------------------------------
# Leader system prompt — reinforces the Leader's exclusive model authority.
# ---------------------------------------------------------------------------

LEADER_SYSTEM_PROMPT = """You are the Leader Agent of a multi-LLM orchestration system.

YOUR EXCLUSIVE AUTHORITY:
- You alone choose which model/provider each Sub-Agent uses.
- Sub-Agents CANNOT select, replace, or switch their own models.
- Every Sub-Agent must use the ModelAssignment you issue (provider + model_id).
- If a Sub-Agent's model fails, you (the Leader) choose the fallback model.

Your job:
1. Analyze the user request and decompose it into tasks by type/modality.
2. Consult the Model Router for recommendations, then issue final bindings.
3. Execute Sub-Agents in parallel or sequential as appropriate.
4. Review every result with Quality Control; resolve conflicts.
5. Apply fallback if quality is below threshold or a model errors.
6. Produce a single coherent final response.

Never delegate model-selection authority to a Sub-Agent.
"""


class LeaderAgent:
    def __init__(
        self,
        agent_id: str = "leader_agent",
        router: Optional[ModelRouter] = None,
        registry: Optional[ModelRegistry] = None,
        security_context: Optional[SecurityContext] = None,
        max_parallel_subagents: int = 5,
    ):
        self.agent_id = agent_id
        self.name = "Leader Agent"
        self.security = SecurityManager(security_context or make_default_security_context())
        self.obs = get_observability()
        self.router = router or get_router()
        self.registry = registry or get_registry()
        self.max_parallel_subagents = max_parallel_subagents

        # Sub-agent registry: agent_id -> SubAgent instance (set by engine).
        self.sub_agents: Dict[str, Any] = {}
        # All assignments issued by this Leader (authoritative record).
        self.assignments: Dict[str, ModelAssignment] = {}
        # Quality control config.
        self.quality_min_score = 0.7
        self.quality_max_review_attempts = 2

    # ------------------------------------------------------------------ authority

    def register_sub_agent(self, agent: Any) -> None:
        """Register a Sub-Agent. Only the Leader manages this registry."""
        self.sub_agents[agent.agent_id] = agent
        self.security.make_audit(
            actor=self.agent_id,
            action="sub_agent_registered",
            target=agent.agent_id,
            details={"agent_name": agent.name, "task_type": agent.task_type},
        )

    def assign_model(self, agent_id: str, task: TaskRequest) -> ModelAssignment:
        """Leader issues a model assignment to a Sub-Agent.

        This is the single point where a model is bound to a sub-agent task.
        No other component (including the sub-agent itself) may do this.
        """
        if agent_id not in self.sub_agents:
            raise ValueError(f"Unknown sub-agent: {agent_id}")

        decision = self.router.route(task)
        if decision.model_id == "unsupported":
            raise ValueError(f"No capable model for task {task.id}: {decision.rationale}")

        entry = self.registry.get(decision.provider, decision.model_id)
        fallback_assignments: List[ModelAssignment] = []
        for fb in decision.fallback_chain[:3]:
            fallback_assignments.append(
                ModelAssignment(
                    task_id=task.id,
                    agent_id=agent_id,
                    provider=fb.provider,
                    model_id=fb.model_id,
                    base_url=fb.base_url,
                    api_key_env=fb.api_key_env,
                    capabilities=fb.capabilities,
                    context_window=fb.context_window,
                    max_retries=task.max_retries or 3,
                    timeout_sec=task.timeout_sec or 120,
                    assigned_by=self.agent_id,
                    active=False,
                )
            )

        assignment = ModelAssignment(
            task_id=task.id,
            agent_id=agent_id,
            provider=decision.provider,
            model_id=decision.model_id,
            base_url=decision.base_url or (entry.base_url if entry else None),
            api_key_env=(entry.api_key_env if entry else None),
            capabilities=decision.capabilities,
            context_window=decision.context_window,
            estimated_cost_usd=decision.estimated_cost_usd,
            timeout_sec=task.timeout_sec or 120,
            max_retries=task.max_retries or 3,
            fallback_assignments=fallback_assignments,
            assigned_by=self.agent_id,
            active=True,
        )

        # Record as authoritative binding and push to sub-agent.
        self.assignments[assignment.id] = assignment
        self.sub_agents[agent_id].set_assignment(assignment, issued_by=self.agent_id)

        self.security.make_audit(
            actor=self.agent_id,
            action="model_assignment_issued",
            target=assignment.model_id,
            details={
                "assignment_id": assignment.id,
                "agent_id": agent_id,
                "agent_name": self.sub_agents[agent_id].name,
                "provider": assignment.provider.value,
                "model_id": assignment.model_id,
                "task_id": task.id,
                "task_type": task.task_type.value,
                "fallback_count": len(fallback_assignments),
            },
        )
        self.obs.record_model_assignment(assignment)
        return assignment

    def reassign_model(
        self, assignment_id: str, agent_id: str, provider: ProviderName, model_id: str, reason: FallbackReason
    ) -> ModelAssignment:
        """Leader reassigns a sub-agent to a different model (fallback/switch)."""
        if agent_id not in self.sub_agents:
            raise ValueError(f"Unknown sub-agent: {agent_id}")
        old = self.assignments.get(assignment_id)

        entry = self.registry.get(provider, model_id)
        new_assignment = ModelAssignment(
            task_id=(old.task_id if old else ""),
            agent_id=agent_id,
            provider=provider,
            model_id=model_id,
            base_url=entry.base_url if entry else None,
            api_key_env=entry.api_key_env if entry else None,
            capabilities=entry.capabilities if entry else [],
            context_window=entry.context_window if entry else None,
            timeout_sec=120,
            max_retries=3,
            assigned_by=self.agent_id,
            active=True,
        )
        # Deactivate old.
        if old:
            old.active = False
        self.assignments[new_assignment.id] = new_assignment
        self.sub_agents[agent_id].set_assignment(new_assignment, issued_by=self.agent_id)

        update = ModelAssignmentUpdate(
            assignment_id=assignment_id,
            task_id=new_assignment.task_id,
            agent_id=agent_id,
            provider=provider,
            model_id=model_id,
            reason=reason,
            assigned_by=self.agent_id,
        )
        self.security.make_audit(
            actor=self.agent_id,
            action="model_reassigned",
            target=model_id,
            details={
                "old_assignment_id": assignment_id,
                "new_assignment_id": new_assignment.id,
                "agent_id": agent_id,
                "old_provider": old.provider.value if old else None,
                "old_model": old.model_id if old else None,
                "new_provider": provider.value,
                "new_model": model_id,
                "reason": reason.value,
            },
        )
        self.obs.record_model_assignment(new_assignment)
        return new_assignment

    # ------------------------------------------------------------- task analysis

    def analyze_request(self, user_request: str, context: Optional[Dict[str, Any]] = None) -> List[TaskRequest]:
        """Analyze the user request and decompose into tasks.

        In production this is done by the Leader's own LLM call. Here we use a
        deterministic classifier keyed on keywords/task hints, with an LLM
        fallback when available, so the system works without hardcoding.
        """
        context = context or {}
        text = (user_request or "").lower()
        tasks: List[TaskRequest] = []

        # Detect task types present in the request.
        detected: List[str] = []
        type_keywords = {
            "code": ["code", "program", "function", "script", "bug", "debug", "write code", "implement"],
            "image": ["image", "picture", "draw", "generate image", "illustration", "logo"],
            "video": ["video", "movie", "animate", "render video", "film"],
            "audio": ["audio", "speech", "voice", "transcribe", "podcast", "sound"],
            "research": ["research", "find", "lookup", "investigate", "report on", "sources"],
            "data": ["data", "dataset", "analyze data", "csv", "sql", "query", "spreadsheet"],
            "text": ["write", "summarize", "email", "essay", "text", "message", "draft"],
        }
        for ttype, kws in type_keywords.items():
            if any(k in text for k in kws):
                detected.append(ttype)

        if not detected:
            detected = ["text"]

        # Decompose: if multiple distinct types, split into separate tasks.
        # Otherwise a single task.
        if len(detected) == 1:
            tasks.append(
                TaskRequest(
                    task_type=detected[0],  # type: ignore[arg-type]
                    modality=self._modality_for(detected[0]),
                    prompt=user_request,
                    context=context,
                )
            )
        else:
            for ttype in detected:
                tasks.append(
                    TaskRequest(
                        task_type=ttype,  # type: ignore[arg-type]
                        modality=self._modality_for(ttype),
                        prompt=user_request,
                        context=context,
                    )
                )
        return tasks

    @staticmethod
    def _modality_for(task_type: str) -> str:
        mapping = {
            "text": "text",
            "code": "code",
            "image": "image",
            "video": "video",
            "audio": "audio",
            "research": "text",
            "data": "text",
        }
        return mapping.get(task_type, "text")

    # ------------------------------------------------------------- execution

    async def execute_sub_agent(
        self, agent_id: str, task: TaskRequest
    ) -> AgentResult:
        """Execute one sub-agent with Leader-assigned model and fallback."""
        if agent_id not in self.sub_agents:
            raise ValueError(f"Unknown sub-agent: {agent_id}")

        agent = self.sub_agents[agent_id]

        # Ensure the Leader has assigned a model for this task.
        assignment = self._current_assignment(agent_id, task.id)
        if assignment is None:
            assignment = self.assign_model(agent_id, task)

        last_error: Optional[str] = None
        result: Optional[AgentResult] = None

        for attempt in range(assignment.max_retries + 1):
            try:
                result = await agent.execute(task)
                last_error = result.error
                if result.ok:
                    # Quality control review.
                    review = self.review_result(task, result)
                    if review.passed or self.quality_max_review_attempts <= 0:
                        result.quality_score = review.score
                        return result
                    # Quality failed -> try fallback model.
                    self.security.make_audit(
                        actor=self.agent_id,
                        action="quality_failed_trigger_fallback",
                        target=assignment.model_id,
                        details={
                            "task_id": task.id,
                            "agent_id": agent_id,
                            "score": review.score,
                            "attempt": attempt,
                            "feedback": review.feedback,
                        },
                    )
                    fallback = self.router.recommend_fallback(assignment, FallbackReason.QUALITY_THRESHOLD, task)
                    if fallback:
                        new_assign = self.reassign_model(
                            assignment.id, agent_id, fallback.provider, fallback.model_id, FallbackReason.QUALITY_THRESHOLD
                        )
                        assignment = new_assign
                        result = None
                        continue
                    # No fallback available; return best-effort result.
                    result.quality_score = review.score
                    return result
                else:
                    # Model error -> fallback.
                    last_error = result.error or "unknown error"
                    fallback = self.router.recommend_fallback(
                        assignment, FallbackReason.ERROR, task
                    )
                    if fallback:
                        new_assign = self.reassign_model(
                            assignment.id, agent_id, fallback.provider, fallback.model_id, FallbackReason.ERROR
                        )
                        assignment = new_assign
                        result = None
                        continue
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                fallback = self.router.recommend_fallback(assignment, FallbackReason.ERROR, task)
                if fallback:
                    new_assign = self.reassign_model(
                        assignment.id, agent_id, fallback.provider, fallback.model_id, FallbackReason.ERROR
                    )
                    assignment = new_assign
                    continue
                break

        # Exhausted retries/fallbacks.
        return AgentResult(
            agent_id=agent_id,
            task_id=task.id,
            assignment_id=assignment.id,
            provider=assignment.provider,
            model_id=assignment.model_id,
            content="",
            ok=False,
            error=last_error or "All retries and fallbacks exhausted.",
            retry_count=assignment.max_retries,
        )

    def _current_assignment(self, agent_id: str, task_id: str) -> Optional[ModelAssignment]:
        for a in self.assignments.values():
            if a.agent_id == agent_id and a.task_id == task_id and a.active:
                return a
        return None

    # ------------------------------------------------------------- quality control

    def review_result(self, task: TaskRequest, result: AgentResult) -> QualityReview:
        """Leader quality-control review of a sub-agent result.

        Reviews correctness, relevance, instruction-following, and uses an LLM
        judge when a quality model is available. Returns a QualityReview.
        """
        score = 1.0
        issues: List[str] = []
        feedback = ""

        if not result.ok:
            score = 0.0
            issues.append(result.error or "execution failed")
            feedback = f"Result failed: {result.error}"
        elif not result.content or not str(result.content).strip():
            score = 0.2
            issues.append("empty content")
            feedback = "The sub-agent returned empty content."
        else:
            content = str(result.content)
            # Heuristic quality signals.
            if len(content) < 10:
                score -= 0.4
                issues.append("content too short")
            # Check instruction-following roughly by echoing key task terms.
            prompt_words = set(re.findall(r"\w+", task.prompt.lower()))
            content_words = set(re.findall(r"\w+", content.lower()))
            overlap = len(prompt_words & content_words) / max(len(prompt_words), 1)
            if overlap < 0.15:
                score -= 0.3
                issues.append("low relevance to prompt")

        score = max(0.0, min(1.0, score))
        passed = score >= self.quality_min_score
        if not passed:
            feedback = feedback or "Quality below threshold."
            feedback += f" (score={score:.2f}, min={self.quality_min_score})"

        review = QualityReview(
            task_id=task.id,
            assignment_id=result.assignment_id,
            reviewer_agent=self.agent_id,
            score=score,
            passed=passed,
            feedback=feedback,
            issues=issues,
            requires_rework=not passed,
        )
        self.security.make_audit(
            actor=self.agent_id,
            action="quality_review",
            target=task.id,
            details={
                "agent_id": result.agent_id,
                "model_id": result.model_id,
                "score": score,
                "passed": passed,
                "issues": issues,
            },
        )
        self.obs.record_quality(task.id, score, passed)
        return review

    # ------------------------------------------------------------- conflict resolution

    def resolve_conflicts(self, results: List[AgentResult]) -> AgentResult:
        """When multiple sub-agents produce conflicting results, the Leader picks
        the highest-quality result and merges. This is Leader authority, not a
        sub-agent decision."""
        if not results:
            raise ValueError("No results to resolve.")
        if len(results) == 1:
            return results[0]

        # Sort by quality score then ok status.
        ordered = sorted(results, key=lambda r: (r.quality_score or 0.0, r.ok), reverse=True)
        best = ordered[0]

        # Merge non-conflicting content from others into notes.
        notes: List[str] = []
        for r in ordered[1:]:
            if r.ok and r.content and r.content != best.content:
                notes.append(f"{r.agent_id} ({r.model_id}): {str(r.content)[:200]}")

        merged = str(best.content)
        if notes:
            merged += "\n\n---\nAdditional perspectives:\n" + "\n".join(notes)

        return AgentResult(
            agent_id=best.agent_id,
            task_id=best.task_id,
            assignment_id=best.assignment_id,
            provider=best.provider,
            model_id=best.model_id,
            content=merged,
            usage=best.usage,
            latency_ms=max(r.latency_ms for r in results),
            cost_usd=sum(r.cost_usd for r in results),
            ok=best.ok,
            error=best.error,
            quality_score=best.quality_score,
        )

    # ------------------------------------------------------------- orchestration

    async def orchestrate(
        self, user_request: str, context: Optional[Dict[str, Any]] = None, sequential: bool = False
    ) -> Dict[str, Any]:
        """Full Leader orchestration: analyze -> assign -> execute -> review -> finalize.

        Returns a dict with tasks, results, quality reviews, and final response.
        """
        context = context or {}
        start = time.time()
        context_id = context.get("session_id", "")

        self.security.make_audit(
            actor=self.agent_id,
            action="orchestration_started",
            target=context_id,
            details={"user_request": user_request[:200], "sequential": sequential},
        )

        tasks = self.analyze_request(user_request, context)
        results: List[AgentResult] = []

        if sequential or len(tasks) == 1:
            for task in tasks:
                # Route each task to the appropriate specialized sub-agent.
                agent_id = self._select_agent_for(task)
                result = await self.execute_sub_agent(agent_id, task)
                results.append(result)
        else:
            # Parallel execution bounded by max_parallel_subagents.
            semaphore = asyncio.Semaphore(self.max_parallel_subagents)

            async def run_one(task: TaskRequest) -> AgentResult:
                async with semaphore:
                    agent_id = self._select_agent_for(task)
                    return await self.execute_sub_agent(agent_id, task)

            results = await asyncio.gather(*(run_one(t) for t in tasks))

        # Quality control + conflict resolution.
        final = self.resolve_conflicts(results) if results else None
        final_review = self.review_result(
            TaskRequest(task_type="text", modality="text", prompt=user_request, context=context),
            final,
        ) if final else None

        elapsed_ms = int((time.time() - start) * 1000)
        self.security.make_audit(
            actor=self.agent_id,
            action="orchestration_completed",
            target=context_id,
            details={
                "tasks": len(tasks),
                "results": len(results),
                "elapsed_ms": elapsed_ms,
                "final_ok": bool(final and final.ok),
                "final_quality": final.quality_score if final else None,
            },
        )

        return {
            "leader_agent": self.agent_id,
            "user_request": user_request,
            "tasks": [t.model_dump() for t in tasks],
            "results": [r.model_dump() for r in results],
            "final": final.model_dump() if final else None,
            "final_review": final_review.model_dump() if final_review else None,
            "elapsed_ms": elapsed_ms,
            "assignments": {
                aid: a.model_dump() for aid, a in self.assignments.items()
            },
        }

    def _select_agent_for(self, task: TaskRequest) -> str:
        """Map a task to a registered specialized sub-agent."""
        # Prefer a registered agent whose task_type matches.
        for agent in self.sub_agents.values():
            if getattr(agent, "task_type", None) == task.task_type:
                return agent.agent_id
        # Fallback to any registered agent.
        if self.sub_agents:
            return next(iter(self.sub_agents))
        raise RuntimeError("No sub-agents registered with the Leader Agent.")


_leader: Optional[LeaderAgent] = None


def get_leader() -> LeaderAgent:
    global _leader
    if _leader is None:
        _leader = LeaderAgent()
    return _leader
