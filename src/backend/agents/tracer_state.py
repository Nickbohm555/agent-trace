from __future__ import annotations

from typing import Any

from langchain_core.messages import AnyMessage
from typing_extensions import TypedDict

from agents.tracer_config import ReasoningLevel, ReasoningPhase


class TracerState(TypedDict, total=False):
    """Canonical tracer state contract for the deep-agent graph."""

    messages: list[AnyMessage]
    current_trace_summary: str | None
    run_id: str
    sandbox_path: str
    local_context: str
    reasoning_phase: ReasoningPhase
    reasoning_level: ReasoningLevel
    reasoning_phase_levels: dict[ReasoningPhase, ReasoningLevel]
    pre_completion_verified: bool
    run_started_at_epoch_seconds: float
    max_runtime_seconds: int
    max_steps: int
    time_budget_notice_interval_steps: int
    agent_step_count: int
    time_budget_last_notice_step: int
    edit_file_counts: dict[str, int]
    loop_detection_threshold: int
    loop_detection_nudged_files: list[str]
    parallel_error_findings: list[dict[str, Any]]
    parallel_error_count: int
    parallel_analysis_completed: bool
    harness_changes: list[dict[str, Any]]
    harness_change_set: dict[str, Any]
