from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import SystemMessage

from agents.tracer_context import build_local_context_message, contains_local_context_message
from schemas.sandbox import SandboxCreateRequest
from services.sandbox_service import SandboxService


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


def test_build_local_context_message_contains_expected_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_clone_to_local_repo(monkeypatch)
    sandbox_service = SandboxService(default_target_repo_url="https://example.com/default.git")
    session = sandbox_service.create_sandbox(SandboxCreateRequest())

    context = build_local_context_message(
        sandbox_service=sandbox_service,
        sandbox_path=session.sandbox_path,
    )

    assert "Sandbox local context:" in context
    assert "sandbox_path:" in context
    assert "cwd: . (repo root)" in context
    assert "top_level_directory_map:" in context
    assert "README.md (file)" in context
    assert "tool_paths:" in context
    assert "python3:" in context

    sandbox_service.teardown_sandbox(session)


def test_contains_local_context_message_detects_context_marker() -> None:
    messages = [
        SystemMessage(content="primary prompt"),
        SystemMessage(content="Sandbox local context:\n- cwd: ."),
    ]
    assert contains_local_context_message(messages)
