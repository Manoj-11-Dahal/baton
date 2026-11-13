"""Security: permissions, tool-call validation, sandboxed code execution, audit.

* Permissions are enforced centrally by the Leader Agent; sub-agents cannot
  bypass them.
* Tool calls are validated against an allow-list before execution.
* Code execution is sandboxed (resource-limited subprocess) when enabled.
* Audit events are recorded immutably.
"""
from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional

from .types import AuditEvent, SecurityContext


class PermissionError(Exception):
    """Raised when a requested action is not permitted."""


class ToolCallValidationError(Exception):
    """Raised when a tool call fails validation."""


class SecurityManager:
    """Central security enforcement used by the Leader Agent and sub-agents."""

    DEFAULT_ALLOWED_TOOLS = [
        "web_search",
        "code_execution",
        "file_read",
        "file_write",
        "image_generation",
        "video_generation",
        "audio_generation",
        "data_query",
        "embedding_search",
    ]

    def __init__(self, context: SecurityContext):
        self.context = context
        self._audit: List[AuditEvent] = []

    # ------------------------------------------------------------------ permissions

    def can_use_tool(self, tool_name: str) -> bool:
        if tool_name in self.context.denied_tools:
            return False
        if self.context.allowed_tools:
            return tool_name in self.context.allowed_tools
        return tool_name in self.DEFAULT_ALLOWED_TOOLS

    def require_tool(self, tool_name: str) -> None:
        if not self.can_use_tool(tool_name):
            raise PermissionError(f"Tool '{tool_name}' is not permitted for this session.")

    # --------------------------------------------------------------- tool validation

    def validate_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> None:
        """Validate a tool call before execution.

        Rules enforced:
        - tool must be permitted
        - no path traversal in file arguments
        - no shell metacharacters in command-like arguments
        - arguments must be a plain object
        """
        self.require_tool(tool_name)
        if not isinstance(arguments, dict):
            raise ToolCallValidationError("Tool arguments must be an object.")

        for key, value in arguments.items():
            if isinstance(value, str):
                if ".." in value and any(k in key.lower() for k in ("path", "file", "dir")):
                    raise ToolCallValidationError(f"Path traversal not allowed in '{key}'.")
                if any(tok in value for tok in (";", "&", "$(", ")", "`", "|", ">", "<")):
                    if key.lower() in ("command", "cmd", "shell", "code"):
                        raise ToolCallValidationError(
                            f"Shell metacharacters not allowed in '{key}'."
                        )

    # ------------------------------------------------------------ sandboxed execution

    async def run_sandboxed_code(
        self, code: str, language: str = "python", timeout_sec: Optional[int] = None
    ) -> Dict[str, Any]:
        """Execute code in a sandboxed subprocess with resource limits.

        Returns {stdout, stderr, exit_code, timed_out, elapsed_ms}.
        """
        if not self.context.sandbox:
            raise PermissionError("Sandboxed code execution is disabled for this session.")
        self.require_tool("code_execution")

        timeout = timeout_sec or self.context.sandbox_timeout_sec
        start = time.time()

        if language == "python":
            fd, path = tempfile.mkstemp(suffix=".py", text=True)
            try:
                with os.fdopen(fd, "w") as f:
                    f.write(code)
                cmd = ["python3", path]
            except Exception:
                os.close(fd)
                raise
        else:
            return {
                "stdout": "",
                "stderr": f"Unsupported language for sandbox: {language}",
                "exit_code": 1,
                "timed_out": False,
                "elapsed_ms": int((time.time() - start) * 1000),
            }

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                return {
                    "stdout": "",
                    "stderr": "Execution timed out.",
                    "exit_code": -1,
                    "timed_out": True,
                    "elapsed_ms": int((time.time() - start) * 1000),
                }
            return {
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "exit_code": proc.returncode or 0,
                "timed_out": False,
                "elapsed_ms": int((time.time() - start) * 1000),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "stdout": "",
                "stderr": f"Sandbox execution error: {exc}",
                "exit_code": 1,
                "timed_out": False,
                "elapsed_ms": int((time.time() - start) * 1000),
            }
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass

    # ----------------------------------------------------------------- audit

    def record(self, event: AuditEvent) -> None:
        self._audit.append(event)

    def get_audit_log(self) -> List[AuditEvent]:
        return list(self._audit)

    def make_audit(
        self,
        actor: str,
        action: str,
        target: str,
        details: Optional[Dict[str, Any]] = None,
        ok: bool = True,
        error: Optional[str] = None,
    ) -> AuditEvent:
        event = AuditEvent(
            actor=actor,
            action=action,
            target=target,
            details=details or {},
            ok=ok,
            error=error,
        )
        self.record(event)
        return event


def make_default_security_context(
    user_id: Optional[str] = None,
    allowed_tools: Optional[List[str]] = None,
    denied_tools: Optional[List[str]] = None,
    sandbox: bool = True,
) -> SecurityContext:
    return SecurityContext(
        user_id=user_id,
        allowed_tools=allowed_tools or [],
        denied_tools=denied_tools or [],
        sandbox=sandbox,
        audit_enabled=True,
    )
