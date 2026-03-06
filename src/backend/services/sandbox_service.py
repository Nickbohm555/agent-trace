from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from typing import Any
from pathlib import Path

from schemas.sandbox import (
    SandboxCommandRequest,
    SandboxCommandResult,
    SandboxCreateRequest,
    SandboxSession,
)

logger = logging.getLogger(__name__)


class SandboxService:
    """Disposable sandbox runtime for tracer-driven repo edits and command execution."""

    def __init__(self, *, default_target_repo_url: str | None = None) -> None:
        self._default_target_repo_url = default_target_repo_url or os.getenv(
            "TRACER_DEFAULT_TARGET_REPO_URL",
            "https://github.com/Nickbohm555/agent-search",
        )

    def create_sandbox(self, request: SandboxCreateRequest) -> SandboxSession:
        target_repo_url = request.target_repo_url or self._default_target_repo_url
        sandbox_id = str(uuid.uuid4())
        sandbox_path = Path(tempfile.mkdtemp(prefix=f"tracer-sandbox-{sandbox_id[:8]}-"))
        repo_path = sandbox_path / "repo"

        logger.info(
            "Creating sandbox",
            extra={
                "sandbox_id": sandbox_id,
                "sandbox_path": str(sandbox_path),
                "target_repo_url": target_repo_url,
                "uses_default_target_repo": request.target_repo_url is None,
            },
        )

        self._clone_repo(target_repo_url=target_repo_url, repo_path=repo_path)

        logger.info(
            "Sandbox created",
            extra={
                "sandbox_id": sandbox_id,
                "repo_path": str(repo_path),
            },
        )
        return SandboxSession(
            sandbox_id=sandbox_id,
            sandbox_path=str(sandbox_path),
            repo_path=str(repo_path),
            target_repo_url=target_repo_url,
        )

    def run_command(self, session: SandboxSession, request: SandboxCommandRequest) -> SandboxCommandResult:
        repo_root = Path(session.repo_path).resolve()
        cwd = repo_root
        if request.cwd:
            cwd = self._resolve_within_root(repo_root, request.cwd)

        logger.info(
            "Running sandbox command",
            extra={
                "sandbox_id": session.sandbox_id,
                "command": request.command,
                "cwd": str(cwd),
                "timeout_seconds": request.timeout_seconds,
            },
        )

        completed = subprocess.run(
            request.command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=request.timeout_seconds,
            check=False,
        )

        logger.info(
            "Sandbox command finished",
            extra={
                "sandbox_id": session.sandbox_id,
                "exit_code": completed.returncode,
                "stdout_bytes": len(completed.stdout.encode("utf-8")),
                "stderr_bytes": len(completed.stderr.encode("utf-8")),
            },
        )

        return SandboxCommandResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def read_file(self, session: SandboxSession, path: str) -> str:
        resolved = self._resolve_within_root(Path(session.repo_path).resolve(), path)
        content = resolved.read_text(encoding="utf-8")
        logger.info(
            "Read file from sandbox",
            extra={
                "sandbox_id": session.sandbox_id,
                "path": path,
                "resolved_path": str(resolved),
                "byte_count": len(content.encode("utf-8")),
            },
        )
        return content

    def list_directory(self, session: SandboxSession, path: str = ".") -> list[dict[str, Any]]:
        resolved = self._resolve_within_root(Path(session.repo_path).resolve(), path)
        if not resolved.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        if not resolved.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {path}")

        entries: list[dict[str, Any]] = []
        repo_root = Path(session.repo_path).resolve()
        for entry in sorted(resolved.iterdir(), key=lambda item: item.name):
            entry_type = "directory" if entry.is_dir() else "file"
            relative_path = str(entry.relative_to(repo_root))
            entries.append(
                {
                    "name": entry.name,
                    "path": relative_path,
                    "type": entry_type,
                    "size_bytes": None if entry_type == "directory" else entry.stat().st_size,
                }
            )

        logger.info(
            "Listed directory in sandbox",
            extra={
                "sandbox_id": session.sandbox_id,
                "path": path,
                "resolved_path": str(resolved),
                "entry_count": len(entries),
            },
        )
        return entries

    def list_directory_by_sandbox_path(
        self,
        *,
        sandbox_path: str,
        path: str = ".",
    ) -> list[dict[str, Any]]:
        session = self._session_from_sandbox_path(sandbox_path)
        return self.list_directory(session, path)

    def read_file_by_sandbox_path(
        self,
        *,
        sandbox_path: str,
        path: str,
    ) -> str:
        session = self._session_from_sandbox_path(sandbox_path)
        return self.read_file(session, path)

    def write_file(self, session: SandboxSession, path: str, content: str) -> None:
        resolved = self._resolve_within_root(Path(session.repo_path).resolve(), path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        logger.info(
            "Wrote file in sandbox",
            extra={
                "sandbox_id": session.sandbox_id,
                "path": path,
                "resolved_path": str(resolved),
                "byte_count": len(content.encode("utf-8")),
            },
        )

    def apply_patch(self, session: SandboxSession, path: str, content: str) -> None:
        """Simple patch primitive: full file replacement at sandbox-relative path."""
        self.write_file(session=session, path=path, content=content)

    def teardown_sandbox(self, session: SandboxSession) -> None:
        sandbox_path = Path(session.sandbox_path)
        logger.info(
            "Tearing down sandbox",
            extra={
                "sandbox_id": session.sandbox_id,
                "sandbox_path": str(sandbox_path),
            },
        )
        shutil.rmtree(sandbox_path, ignore_errors=True)

    @staticmethod
    def _resolve_within_root(root: Path, relative_path: str) -> Path:
        resolved = (root / relative_path).resolve()
        if root != resolved and root not in resolved.parents:
            raise ValueError(f"Path escapes sandbox root: {relative_path}")
        return resolved

    @staticmethod
    def _clone_repo(*, target_repo_url: str, repo_path: Path) -> None:
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", target_repo_url, str(repo_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            logger.exception(
                "Failed to clone target repo for sandbox",
                extra={
                    "target_repo_url": target_repo_url,
                    "stderr": exc.stderr,
                    "stdout": exc.stdout,
                    "exit_code": exc.returncode,
                },
            )
            raise RuntimeError(f"Failed to clone target repo: {target_repo_url}") from exc

    @staticmethod
    def _session_from_sandbox_path(sandbox_path: str) -> SandboxSession:
        root = Path(sandbox_path).resolve()
        repo_path = root / "repo"
        if not repo_path.exists():
            raise FileNotFoundError(f"Sandbox repo path not found: {repo_path}")
        return SandboxSession(
            sandbox_id=root.name,
            sandbox_path=str(root),
            repo_path=str(repo_path),
            target_repo_url="unknown",
        )
