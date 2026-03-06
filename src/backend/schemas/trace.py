from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NormalizedTraceError(BaseModel):
    message: str | None = None
    error_type: str | None = None
    stacktrace: str | None = None


class NormalizedTraceSpan(BaseModel):
    span_id: str
    name: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    latency_ms: float | None = None
    status_message: str | None = None
    input_payload: Any | None = None
    output_payload: Any | None = None
    error: NormalizedTraceError | None = None


class NormalizedTrace(BaseModel):
    trace_id: str
    run_id: str | None = None
    name: str | None = None
    environment: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    latency_ms: float | None = None
    input_payload: Any | None = None
    output_payload: Any | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    total_tokens: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    error: NormalizedTraceError | None = None
    spans: list[NormalizedTraceSpan] = Field(default_factory=list)


class TraceQueryFilters(BaseModel):
    trace_ids: list[str] | None = None
    run_name: str | None = None
    from_timestamp: datetime | None = None
    to_timestamp: datetime | None = None
    limit: int = Field(default=50, ge=1, le=500)
    environment: str | None = None


class TraceStorageQuery(BaseModel):
    trace_ids: list[str] | None = None
    run_id: str | None = None
    experiment_name: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class StoredTrace(BaseModel):
    trace_id: str
    run_id: str | None = None
    experiment_name: str | None = None
    environment: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    latency_ms: float | None = None
    input_payload: Any | None = None
    output_payload: Any | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    total_tokens: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    raw_payload: dict[str, Any] | None = None
    spans: list[NormalizedTraceSpan] = Field(default_factory=list)
