from __future__ import annotations

from pathlib import Path

import pytest

from schemas.sandbox import SandboxCreateRequest
from services.sandbox_service import SandboxService
from tools.sandbox_tools import build_run_command_tool


def _mock_clone_to_local_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_clone(*, target_repo_url: str, repo_path: Path) -> None:
        repo_path.mkdir(parents=True, exist_ok=True)
        (repo_path / "README.md").write_text(
            f"cloned from {target_repo_url}\n",
            encoding="utf-8",
        )
        (repo_path / "src").mkdir(parents=True, exist_ok=True)
        (repo_path / "src" / "app.py").write_text("print('sandbox')\n", encoding="utf-8")

    monkeypatch.setattr(SandboxService, "_clone_repo", staticmethod(fake_clone))


def test_run_command_tool_executes_echo_in_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_clone_to_local_repo(monkeypatch)
    service = SandboxService(default_target_repo_url="https://example.com/default.git")
    session = service.create_sandbox(SandboxCreateRequest())

    tool = build_run_command_tool(service)
    result = tool.invoke(
        {
            "sandbox_path": session.sandbox_path,
            "command": ["sh", "-c", "echo hello-from-sandbox"],
            "timeout_seconds": 10,
        }
    )

    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "hello-from-sandbox"
    assert result["stderr"] == ""
    assert result["sandbox_path"] == session.sandbox_path

    service.teardown_sandbox(session)
