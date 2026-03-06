from __future__ import annotations

from pathlib import Path

import pytest

from schemas.sandbox import SandboxCreateRequest
from services.sandbox_service import SandboxService
from tools.codebase_tools import build_edit_file_tool, build_list_directory_tool, build_read_file_tool


def _mock_clone_to_local_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_clone(*, target_repo_url: str, repo_path: Path) -> None:
        repo_path.mkdir(parents=True, exist_ok=True)
        (repo_path / "README.md").write_text(
            f"cloned from {target_repo_url}\n",
            encoding="utf-8",
        )
        nested_dir = repo_path / "src"
        nested_dir.mkdir(parents=True, exist_ok=True)
        (nested_dir / "app.py").write_text("print('ok')\n", encoding="utf-8")

    monkeypatch.setattr(SandboxService, "_clone_repo", staticmethod(fake_clone))


def test_list_directory_tool_lists_sandbox_repo_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_clone_to_local_repo(monkeypatch)
    service = SandboxService(default_target_repo_url="https://example.com/default.git")
    session = service.create_sandbox(SandboxCreateRequest())

    tool = build_list_directory_tool(service)
    result = tool.invoke({"sandbox_path": session.sandbox_path, "path": "."})

    names = [entry["name"] for entry in result["entries"]]
    assert names == ["README.md", "src"]
    assert result["count"] == 2

    service.teardown_sandbox(session)


def test_read_file_tool_returns_content_from_sandbox_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_clone_to_local_repo(monkeypatch)
    service = SandboxService(default_target_repo_url="https://example.com/default.git")
    session = service.create_sandbox(SandboxCreateRequest())

    tool = build_read_file_tool(service)
    result = tool.invoke({"sandbox_path": session.sandbox_path, "path": "src/app.py"})

    assert result["path"] == "src/app.py"
    assert "print('ok')" in result["content"]
    assert result["byte_count"] > 0

    service.teardown_sandbox(session)


def test_edit_file_tool_updates_content_in_sandbox_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_clone_to_local_repo(monkeypatch)
    service = SandboxService(default_target_repo_url="https://example.com/default.git")
    session = service.create_sandbox(SandboxCreateRequest())

    edit_tool = build_edit_file_tool(service)
    edit_result = edit_tool.invoke(
        {
            "sandbox_path": session.sandbox_path,
            "path": "src/app.py",
            "content": "print('edited')\n",
        }
    )

    read_tool = build_read_file_tool(service)
    read_result = read_tool.invoke({"sandbox_path": session.sandbox_path, "path": "src/app.py"})

    assert edit_result["status"] == "updated"
    assert edit_result["path"] == "src/app.py"
    assert "print('edited')" in read_result["content"]

    service.teardown_sandbox(session)
