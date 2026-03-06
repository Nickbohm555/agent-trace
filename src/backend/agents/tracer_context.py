from __future__ import annotations

import logging

from services.sandbox_service import SandboxService

logger = logging.getLogger(__name__)

_CONTEXT_MARKER = "Sandbox local context:"


def contains_local_context_message(messages: list[object]) -> bool:
    return any(_CONTEXT_MARKER in str(getattr(message, "content", "")) for message in messages)


def build_local_context_message(
    *,
    sandbox_service: SandboxService,
    sandbox_path: str,
) -> str:
    logger.info("Building tracer local context", extra={"sandbox_path": sandbox_path})
    entries = sandbox_service.list_directory_by_sandbox_path(sandbox_path=sandbox_path, path=".")
    root_entry_lines = [
        f"- {entry['name']} ({entry['type']})"
        for entry in entries[:20]
    ]
    if len(entries) > 20:
        root_entry_lines.append(f"- ... {len(entries) - 20} more entries")

    command_checks = {
        "python3": "which python3 || true",
        "python": "which python || true",
        "pytest": "which pytest || true",
        "node": "which node || true",
        "npm": "which npm || true",
        "git": "which git || true",
        "uv": "which uv || true",
    }
    detected_tools: dict[str, str] = {}
    for tool_name, command in command_checks.items():
        result = sandbox_service.run_command_by_sandbox_path(
            sandbox_path=sandbox_path,
            command=["sh", "-lc", command],
            timeout_seconds=15,
        )
        detected_tools[tool_name] = result.stdout.strip() or "not found"

    tool_lines = [f"- {tool}: {path}" for tool, path in detected_tools.items()]
    context_message = "\n".join(
        [
            _CONTEXT_MARKER,
            f"- sandbox_path: {sandbox_path}",
            "- cwd: . (repo root)",
            "- top_level_directory_map:",
            *root_entry_lines,
            "- tool_paths:",
            *tool_lines,
        ]
    )
    logger.info(
        "Built tracer local context",
        extra={
            "sandbox_path": sandbox_path,
            "top_level_entries": len(entries),
            "tools_checked": len(command_checks),
        },
    )
    return context_message
