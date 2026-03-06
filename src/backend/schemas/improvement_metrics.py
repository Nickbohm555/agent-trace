from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EvaluationRunMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: list[str] = Field(min_length=1)
    cwd: str | None = None
    timeout_seconds: int = Field(ge=1, le=900)
    exit_code: int
    success: bool
    duration_ms: int = Field(ge=0)
    tests_passed: int | None = Field(default=None, ge=0)
    tests_failed: int | None = Field(default=None, ge=0)
    tests_skipped: int | None = Field(default=None, ge=0)
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""


class ImprovementDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exit_code_delta: int
    success_delta: int
    tests_passed_delta: int | None = None
    tests_failed_delta: int | None = None
    tests_skipped_delta: int | None = None
    score_before: int | None = None
    score_after: int | None = None
    score_delta: int | None = None


class ImprovementMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline: EvaluationRunMetrics
    post_change: EvaluationRunMetrics
    delta: ImprovementDelta
    improved: bool
