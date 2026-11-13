"""Base Sub-Agent class.

A Sub-Agent executes a task using ONLY the model assigned by the Leader Agent.
It has no authority to select, replace, or switch its model. Any attempt to
do so is rejected and logged as a security event.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from ..adapters.base import ModelCall, ModelResponse, get_adapter
from ..core.observability import get_observability
from ..core.security import SecurityManager, make_default_security_context
from ..core.types import (
    AgentResult,
    FallbackReason,
    ModelAssignment,
    Modality,
    ProviderName,
    TaskRequest,
)


class SubAgent:
    """Base class for all specialized sub-agents.

    Invariant: self.assignment is set by the Leader Agent and is the sole
    model the sub-agent may use. There is no method for a sub-agent to change
    its own model.
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str,
        task_type: str,
        system_prompt: str,
        security_context: Optional[Any] = None,
    ):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.task_type = task_type
        self.system_prompt = system_prompt
        self.security = SecurityManager(security_context or make_default_security_context())
        self.obs = get_observability()
        self.assignment: Optional[ModelAssignment] = None
        self._call_count = 0

    # ------------------------------------------------------------------ model authority

    def set_assignment(self, assignment: ModelAssignment, issued_by: str = "leader_agent") -> None:
        """Called ONLY by the Leader Agent to bind this sub-agent to a model."""
        if issued_by != "leader_agent":
            self.security.make_audit(
                actor=f"sub_agent:{self.agent_id}",
                action="unauthorized_model_assignment_attempt",
                target=assignment.model_id,
                details={"issued_by": issued_by},
                ok=False,
                error="Only the Leader Agent may assign models.",
            )
            raise PermissionError("Only the Leader Agent may assign models to a sub-agent.")
        self.assignment = assignment
        self.security.make_audit(
            actor="leader_agent",
            action="model_assigned",
            target=assignment.model_id,
            details={"agent_id": self.agent_id, "agent_name": self.name, "provider": assignment.provider},
        )

    def _require_assignment(self) -> ModelAssignment:
        if self.assignment is None:
            raise RuntimeError(
                f"Sub-Agent '{self.name}' ({self.agent_id}) has no model assignment. "
                "The Leader Agent must assign a model before execution."
            )
        return self.assignment

    def _enforce_model_authority(self, requested_provider: ProviderName, requested_model: str) -> None:
        """Reject any sub-agent attempt to independently select/switch models."""
        assignment = self._require_assignment()
        if requested_provider != assignment.provider or requested_model != assignment.model_id:
            self.security.make_audit(
                actor=f"sub_agent:{self.agent_id}",
                action="unattempted_model_switch",
                target=requested_model,
                details={
                    "assigned_provider": assignment.provider,
                    "assigned_model": assignment.model_id,
                    "requested_provider": requested_provider,
                    "requested_model": requested_model,
                },
                ok=False,
                error="Sub-agents cannot independently select or switch models.",
            )
            raise PermissionError(
                f"Sub-Agent '{self.name}' cannot switch from {assignment.provider}/{assignment.model_id} "
                f"to {requested_provider}/{requested_model}. Only the Leader Agent may assign models."
            )

    # ---------------------------------------------------------------- execution

    async def execute(self, task: TaskRequest) -> AgentResult:
        """Execute the task using the Leader-assigned model only."""
        assignment = self._require_assignment()
        start = time.time()
        self._call_count += 1

        # Build messages: system prompt + task prompt + shared context.
        messages = [
            {"role": "system", "content": self.system_prompt},
        ]
        if task.context:
            messages.append({"role": "system", "content": f"Shared task context: {task.context}"})
        messages.append({"role": "user", "content": task.prompt})

        call = ModelCall(
            model_id=assignment.model_id,
            provider=assignment.provider,
            messages=messages,
            base_url=assignment.base_url,
            api_key=os_api_key(assignment.provider, assignment.api_key_env),
            temperature=0.7,
            max_output_tokens=4096,
            timeout_sec=assignment.timeout_sec,
            metadata={"agent_id": self.agent_id, "agent_name": self.name, "task_id": task.id},
        )

        adapter = get_adapter(assignment.provider.value)
        try:
            response = await adapter.call(call)
        except Exception as exc:  # noqa: BLE001
            response = ModelResponse(
                model_id=assignment.model_id,
                provider=assignment.provider,
                content="",
                ok=False,
                error=str(exc),
            )

        latency_ms = int((time.time() - start) * 1000)
        return AgentResult(
            agent_id=self.agent_id,
            task_id=task.id,
            assignment_id=assignment.id,
            provider=assignment.provider,
            model_id=assignment.model_id,
            content=response.content,
            structured=None,
            usage=response.usage,
            latency_ms=response.latency_ms or latency_ms,
            cost_usd=response.cost_usd,
            ok=response.ok,
            error=response.error,
            fallback_used=False,
            retry_count=0,
        )


def os_api_key(provider: ProviderName, api_key_env: Optional[str] = None) -> Optional[str]:
    import os

    env = api_key_env or {
        ProviderName.OPENAI: "OPENAI_API_KEY",
        ProviderName.ANTHROPIC: "ANTHROPIC_API_KEY",
        ProviderName.GOOGLE: "GOOGLE_API_KEY",
        ProviderName.GEMINI: "GEMINI_API_KEY",
        ProviderName.LLAMA: "LLAMA_API_KEY",
        ProviderName.MISTRAL: "MISTRAL_API_KEY",
        ProviderName.DEEPSEEK: "DEEPSEEK_API_KEY",
        ProviderName.QWEN: "QWEN_API_KEY",
        ProviderName.LOCAL: "LOCAL_LLM_API_KEY",
    }.get(provider)
    return os.environ.get(env) if env else None
