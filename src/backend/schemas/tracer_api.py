from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.harness_changes import HarnessChangeSet
from schemas.improvement_metrics import ImprovementMetrics


class TracerRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str | None = None
    trace_ids: list[str] | None = None
    target_repo_url: str | None = None
    run_name: str | None = None
    from_timestamp: datetime | None = None
    to_timestamp: datetime | None = None
    limit: int = Field(default=50, ge=1, le=500)
    environment: str | None = None
    evaluation_command: list[str] | None = None
    evaluation_cwd: str | None = None
    evaluation_timeout_seconds: int = Field(default=900, ge=1, le=3600)
    max_runtime_seconds: int | None = Field(default=None, ge=1, le=7200)
    max_steps: int | None = Field(default=None, ge=1, le=200)

    @model_validator(mode="after")
    def validate_run_or_trace_ids(self) -> TracerRunRequest:
        has_run_id = bool(self.run_id and self.run_id.strip())
        has_trace_ids = bool(self.trace_ids)
        if not has_run_id and not has_trace_ids:
            raise ValueError("Provide at least one of run_id or trace_ids.")
        return self


class TracerRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    target_repo_url: str
    trace_ids: list[str]
    fetched_trace_count: int
    persisted_trace_count: int
    loaded_trace_count: int
    harness_change_set: HarnessChangeSet
    improvement_metrics: ImprovementMetrics | None = None
