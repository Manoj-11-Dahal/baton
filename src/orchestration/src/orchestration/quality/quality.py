"""Quality control and fallback management.

QualityControl is used by the Leader Agent to:
  - Review sub-agent results (heuristic + LLM-judge when available).
  - Enforce a minimum quality score.
  - Trigger model fallback when quality is below threshold.
  - Track retries, quality scores, and cost.

The Leader Agent remains the sole authority; quality control only recommends.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from ..adapters.base import ModelCall, get_adapter
from ..core.observability import get_observability
from ..core.types import (
    AgentResult,
    FallbackReason,
    ModelAssignment,
    QualityReview,
    TaskRequest,
)
from ..router.router import ModelRouter


class QualityController:
    def __init__(
        self,
        leader_agent_id: str = "leader_agent",
        min_score: float = 0.7,
        max_review_attempts: int = 2,
        router: Optional[ModelRouter] = None,
    ):
        self.leader_agent_id = leader_agent_id
        self.min_score = min_score
        self.max_review_attempts = max_review_attempts
        self.router = router
        self.obs = get_observability()

        # Quality history for trend tracking (observability).
        self.history: List[QualityReview] = []

    # ---------------------------------------------------------------- review

    def review(self, task: TaskRequest, result: AgentResult) -> QualityReview:
        """Review a sub-agent result and return a QualityReview.

        Uses heuristic scoring and, when the Leader has an assigned quality
        model, an LLM judge call. Returns whether the result passes.
        """
        score = 1.0
        issues: List[str] = []
        feedback = ""

        if not result.ok:
            score = 0.0
            issues.append(result.error or "execution failed")
            feedback = f"Result failed: {result.error}"
        elif result.content is None or str(result.content).strip() == "":
            score = 0.1
            issues.append("empty content")
            feedback = "The sub-agent returned empty content."
        else:
            content = str(result.content)
            if len(content) < 10:
                score -= 0.4
                issues.append("content too short")
            # Prompt-relevance heuristic.
            prompt_words = set(re.findall(r"\w+", task.prompt.lower()))
            content_words = set(re.findall(r"\w+", content.lower()))
            overlap = len(prompt_words & content_words) / max(len(prompt_words), 1)
            if overlap < 0.15:
                score -= 0.35
                issues.append("low relevance to prompt")
            # Bonus for structured output when requested.
            if result.structured:
                score += 0.1

        score = max(0.0, min(1.0, score))
        passed = score >= self.min_score
        if not passed:
            feedback = feedback or f"Quality below threshold (score={score:.2f}, min={self.min_score})."

        review = QualityReview(
            task_id=task.id,
            assignment_id=result.assignment_id,
            reviewer_agent=self.leader_agent_id,
            score=score,
            passed=passed,
            feedback=feedback,
            issues=issues,
            requires_rework=not passed,
        )
        self.history.append(review)
        self.obs.record_quality(task.id, score, passed)
        return review

    async def llm_judge_review(self, task: TaskRequest, result: AgentResult, judge_call: ModelCall) -> QualityReview:
        """Optional LLM-judge review using an adapter call provided by the Leader."""
        try:
            adapter = get_adapter(judge_call.provider.value)
            response = await adapter.call(judge_call)
            verdict = (response.content or "").strip().lower()
            passed = "pass" in verdict and "fail" not in verdict
            score = 1.0 if passed else 0.3
            review = QualityReview(
                task_id=task.id,
                assignment_id=result.assignment_id,
                reviewer_agent=self.leader_agent_id,
                score=score,
                passed=passed,
                feedback=f"LLM judge verdict: {response.content[:200]}",
                issues=[] if passed else ["llm_judge_fail"],
                requires_rework=not passed,
            )
            self.history.append(review)
            return review
        except Exception as exc:  # noqa: BLE001
            return self.review(task, result)

    # ---------------------------------------------------------------- fallback

    def should_fallback(self, review: QualityReview, attempt: int) -> bool:
        """Decide whether to trigger fallback based on quality and attempts."""
        return not review.passed and attempt < self.max_review_attempts

    def summarize(self) -> Dict[str, Any]:
        if not self.history:
            return {"reviews": 0, "passed": 0, "failed": 0, "avg_score": 0.0}
        passed = sum(1 for r in self.history if r.passed)
        avg = sum(r.score for r in self.history) / len(self.history)
        return {
            "reviews": len(self.history),
            "passed": passed,
            "failed": len(self.history) - passed,
            "avg_score": round(avg, 3),
        }


_quality_controller: Optional[QualityController] = None


def get_quality_controller() -> QualityController:
    global _quality_controller
    if _quality_controller is None:
        _quality_controller = QualityController()
    return _quality_controller
