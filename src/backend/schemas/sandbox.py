from __future__ import annotations

from pydantic import BaseModel, Field


class SandboxCreateRequest(BaseModel):
    target_repo_url: str | None = None


class SandboxSession(BaseModel):
    sandbox_id: str
    sandbox_path: str
    repo_path: str
    target_repo_url: str


class SandboxCommandRequest(BaseModel):
    command: list[str] = Field(min_length=1)
    cwd: str | None = None
    timeout_seconds: int = Field(default=120, ge=1, le=900)


class SandboxCommandResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
