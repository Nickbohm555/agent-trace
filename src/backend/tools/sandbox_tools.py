from __future__ import annotations

import logging
from dataclasses import dataclass

from langchain_core.tools import StructuredTool

from services.sandbox_service import SandboxService

logger = logging.getLogger(__name__)


@dataclass
class SandboxTools:
    """Sandbox-backed command execution tools."""

    sandbox_service: SandboxService

    def run_command(
        self,
        *,
        sandbox_path: str,
        command: list[str],
        timeout_seconds: int = 120,
        cwd: str | None = None,
    ) -> dict[str, object]:
        result = self.sandbox_service.run_command_by_sandbox_path(
            sandbox_path=sandbox_path,
            command=command,
            timeout_seconds=timeout_seconds,
            cwd=cwd,
        )
        logger.info(
            "run_command tool completed",
            extra={
                "sandbox_path": sandbox_path,
                "command": command,
                "cwd": cwd,
                "timeout_seconds": timeout_seconds,
                "exit_code": result.exit_code,
                "stdout_bytes": len(result.stdout.encode("utf-8")),
                "stderr_bytes": len(result.stderr.encode("utf-8")),
            },
        )
        return {
            "sandbox_path": sandbox_path,
            "command": command,
            "cwd": cwd,
            "timeout_seconds": timeout_seconds,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }


def build_run_command_tool(sandbox_service: SandboxService) -> StructuredTool:
    adapter = SandboxTools(sandbox_service=sandbox_service)
    return StructuredTool.from_function(
        func=adapter.run_command,
        name="run_command",
        description=(
            "Run a shell command in the active sandbox repo. "
            "Accepts command argv list, optional cwd, and timeout_seconds."
        ),
    )
