from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import StructuredTool

from services.sandbox_service import SandboxService

logger = logging.getLogger(__name__)


@dataclass
class CodebaseTools:
    """Sandbox-backed filesystem tools for directory listing and file reads."""

    sandbox_service: SandboxService

    def list_directory(self, *, sandbox_path: str, path: str = ".") -> dict[str, Any]:
        entries = self.sandbox_service.list_directory_by_sandbox_path(
            sandbox_path=sandbox_path,
            path=path,
        )
        logger.info(
            "list_directory tool completed",
            extra={"sandbox_path": sandbox_path, "path": path, "entry_count": len(entries)},
        )
        return {
            "sandbox_path": sandbox_path,
            "path": path,
            "count": len(entries),
            "entries": entries,
        }

    def read_file(self, *, sandbox_path: str, path: str) -> dict[str, Any]:
        content = self.sandbox_service.read_file_by_sandbox_path(
            sandbox_path=sandbox_path,
            path=path,
        )
        logger.info(
            "read_file tool completed",
            extra={"sandbox_path": sandbox_path, "path": path, "byte_count": len(content.encode("utf-8"))},
        )
        return {
            "sandbox_path": sandbox_path,
            "path": path,
            "content": content,
            "byte_count": len(content.encode("utf-8")),
        }


def build_list_directory_tool(sandbox_service: SandboxService) -> StructuredTool:
    adapter = CodebaseTools(sandbox_service=sandbox_service)
    return StructuredTool.from_function(
        func=adapter.list_directory,
        name="list_directory",
        description="List files and directories under a path within the active sandbox repo.",
    )


def build_read_file_tool(sandbox_service: SandboxService) -> StructuredTool:
    adapter = CodebaseTools(sandbox_service=sandbox_service)
    return StructuredTool.from_function(
        func=adapter.read_file,
        name="read_file",
        description="Read a file from the active sandbox repo using a sandbox-relative path.",
    )
