"""Tests for core/security.py — permissions, tool validation, sandbox, audit."""
import asyncio

import pytest

from orchestration.core.security import (
    PermissionError,
    SecurityManager,
    ToolCallValidationError,
    make_default_security_context,
)
from orchestration.core.types import SecurityContext


def test_security_manager_default_allowed_tools():
    """Default allowed tools should be present."""
    sm = SecurityManager(SecurityContext())
    for tool in [
        "web_search",
        "code_execution",
        "file_read",
        "file_write",
        "image_generation",
        "video_generation",
        "audio_generation",
        "data_query",
        "embedding_search",
    ]:
        assert sm.can_use_tool(tool) is True


def test_security_manager_denied_tool():
    """A tool in denied_tools should not be usable."""
    sc = SecurityContext(denied_tools=["file_write"])
    sm = SecurityManager(sc)
    assert sm.can_use_tool("file_write") is False
    assert sm.can_use_tool("file_read") is True


def test_security_manager_allowed_tools_override():
    """When allowed_tools is set, only those tools are usable."""
    sc = SecurityContext(allowed_tools=["web_search", "file_read"])
    sm = SecurityManager(sc)
    assert sm.can_use_tool("web_search") is True
    assert sm.can_use_tool("file_read") is True
    assert sm.can_use_tool("code_execution") is False


def test_security_manager_require_tool_raises():
    """require_tool should raise PermissionError for denied tools."""
    sc = SecurityContext(denied_tools=["code_execution"])
    sm = SecurityManager(sc)
    with pytest.raises(PermissionError):
        sm.require_tool("code_execution")


def test_security_manager_validate_tool_call_ok():
    """validate_tool_call should pass for valid calls."""
    sc = SecurityContext()
    sm = SecurityManager(sc)
    sm.validate_tool_call("file_read", {"path": "/tmp/foo.txt"})


def test_security_manager_validate_tool_call_path_traversal():
    """validate_tool_call should block path traversal."""
    sc = SecurityContext()
    sm = SecurityManager(sc)
    with pytest.raises(ToolCallValidationError):
        sm.validate_tool_call("file_read", {"path": "../../../etc/passwd"})


def test_security_manager_validate_tool_call_shell_metacharacters():
    """validate_tool_call should block shell metacharacters in command/code fields."""
    sc = SecurityContext()
    sm = SecurityManager(sc)
    with pytest.raises(ToolCallValidationError):
        sm.validate_tool_call("code_execution", {"code": "import os; os.system('rm -rf /')"})


def test_security_manager_validate_tool_call_not_dict():
    """validate_tool_call should reject non-dict arguments."""
    sc = SecurityContext()
    sm = SecurityManager(sc)
    with pytest.raises(ToolCallValidationError):
        sm.validate_tool_call("file_read", "/tmp/foo.txt")  # type: ignore[arg-type]


def test_security_manager_audit_record():
    """record() and get_audit_log() should track audit events."""
    sc = SecurityContext()
    sm = SecurityManager(sc)
    assert sm.get_audit_log() == []

    event = sm.make_audit(
        actor="leader_agent",
        action="test_action",
        target="target1",
        details={"k": "v"},
        ok=True,
    )
    log = sm.get_audit_log()
    assert len(log) == 1
    assert log[0].actor == "leader_agent"
    assert log[0].action == "test_action"
    assert log[0].target == "target1"
    assert log[0].details == {"k": "v"}
    assert log[0].ok is True
    assert event is log[0]


def test_security_manager_audit_error():
    """Audit events can record errors."""
    sc = SecurityContext()
    sm = SecurityManager(sc)
    sm.make_audit(
        actor="sub_agent:test",
        action="unauthorized_switch",
        target="gpt-4",
        ok=False,
        error="not permitted",
    )
    log = sm.get_audit_log()
    assert len(log) == 1
    assert log[0].ok is False
    assert log[0].error == "not permitted"


def test_make_default_security_context():
    """make_default_security_context should create a secure context."""
    sc = make_default_security_context(user_id="user1", sandbox=True)
    assert sc.user_id == "user1"
    assert sc.sandbox is True
    assert sc.audit_enabled is True


def test_make_default_security_context_allowed_tools():
    sc = make_default_security_context(allowed_tools=["web_search"])
    assert sc.allowed_tools == ["web_search"]


@pytest.mark.asyncio
async def test_run_sandboxed_code_disabled():
    """run_sandboxed_code should raise PermissionError when sandbox disabled."""
    sc = SecurityContext(sandbox=False)
    sm = SecurityManager(sc)
    with pytest.raises(PermissionError):
        await sm.run_sandboxed_code("print(1)")

@pytest.mark.asyncio
async def test_run_sandboxed_code_requires_permission():
    """run_sandboxed_code should require code_execution tool."""
    sc = SecurityContext(sandbox=True, denied_tools=["code_execution"])
    sm = SecurityManager(sc)
    with pytest.raises(PermissionError):
        await sm.run_sandboxed_code("print(1)")


@pytest.mark.asyncio
async def test_run_sandboxed_code_python():
    """run_sandboxed_code should execute simple python code."""
    sc = SecurityContext(sandbox=True)
    sm = SecurityManager(sc)
    result = await sm.run_sandboxed_code("print(2 + 2)")
    assert result["exit_code"] == 0
    assert "4" in result["stdout"]


@pytest.mark.asyncio
async def test_run_sandboxed_code_unsupported_language():
    """Unsupported language should return an error result."""
    sc = SecurityContext(sandbox=True)
    sm = SecurityManager(sc)
    result = await sm.run_sandboxed_code("echo hi", language="bash")
    assert result["exit_code"] == 1
    assert "Unsupported language" in result["stderr"]


@pytest.mark.asyncio
async def test_run_sandboxed_code_timeout():
    """run_sandboxed_code should timeout long-running code."""
    sc = SecurityContext(sandbox=True)
    sm = SecurityManager(sc)
    result = await sm.run_sandboxed_code(
        "import time; time.sleep(10)", timeout_sec=1
    )
    assert result["timed_out"] is True
    assert result["exit_code"] == -1
