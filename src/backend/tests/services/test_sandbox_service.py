from __future__ import annotations

from pathlib import Path

import pytest

from schemas.sandbox import SandboxCommandRequest, SandboxCreateRequest
from services.sandbox_service import SandboxService


def _mock_clone_to_local_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_clone(*, target_repo_url: str, repo_path: Path) -> None:
        repo_path.mkdir(parents=True, exist_ok=True)
        (repo_path / "README.md").write_text(
            f"cloned from {target_repo_url}\n", encoding="utf-8"
        )

    monkeypatch.setattr(SandboxService, "_clone_repo", staticmethod(fake_clone))


def test_create_sandbox_uses_default_repo_when_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_clone_to_local_repo(monkeypatch)
    monkeypatch.setenv("TRACER_DEFAULT_TARGET_REPO_URL", "https://example.com/default.git")

    service = SandboxService()
    session = service.create_sandbox(SandboxCreateRequest())

    assert session.target_repo_url == "https://example.com/default.git"
    assert Path(session.repo_path).exists()

    service.teardown_sandbox(session)
    assert not Path(session.sandbox_path).exists()


def test_sandbox_write_read_run_and_teardown(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_clone_to_local_repo(monkeypatch)

    service = SandboxService(default_target_repo_url="https://example.com/default.git")
    session = service.create_sandbox(
        SandboxCreateRequest(target_repo_url="https://example.com/custom.git")
    )

    service.write_file(session, "notes/output.txt", "sandbox-data")
    assert service.read_file(session, "notes/output.txt") == "sandbox-data"

    command_result = service.run_command(
        session,
        SandboxCommandRequest(command=["sh", "-c", "echo sandbox-ok"]),
    )

    assert command_result.exit_code == 0
    assert command_result.stdout.strip() == "sandbox-ok"

    service.teardown_sandbox(session)
    assert not Path(session.sandbox_path).exists()


def test_read_file_rejects_path_escape(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_clone_to_local_repo(monkeypatch)

    service = SandboxService(default_target_repo_url="https://example.com/default.git")
    session = service.create_sandbox(SandboxCreateRequest())

    with pytest.raises(ValueError, match="Path escapes sandbox root"):
        service.read_file(session, "../outside.txt")

    service.teardown_sandbox(session)
