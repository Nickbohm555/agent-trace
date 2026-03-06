from __future__ import annotations

import logging
import time

from langchain_core.messages import AIMessage, AnyMessage, SystemMessage

from agents.tracer_state import TracerState

logger = logging.getLogger(__name__)
DEFAULT_TIME_BUDGET_NOTICE_INTERVAL_STEPS = 3
DEFAULT_LOOP_DETECTION_THRESHOLD = 10

_PRE_COMPLETION_CHECKLIST = "\n".join(
    [
        "Pre-completion verification checklist:",
        "- Before finishing, run a concrete verification pass against the task spec.",
        "- Execute relevant tests or commands and inspect their output.",
        "- Confirm implementation behavior matches the requested scope and constraints.",
        "- If verification fails, fix issues and re-verify before finishing.",
    ]
)


def build_pre_completion_checklist_message(state: TracerState) -> str:
    run_id = state.get("run_id", "unknown")
    trace_summary = state.get("current_trace_summary")
    task_spec_snippet = state.get("task_spec_snippet")
    trace_ids = state.get("trace_ids") or []
    extra_lines = [f"- run_id: {run_id}"]
    if trace_ids:
        extra_lines.append(f"- trace_ids: {', '.join(trace_ids)}")
    if trace_summary:
        extra_lines.append(f"- current_trace_summary: {trace_summary}")
    if task_spec_snippet:
        extra_lines.append(f"- task_spec_snippet: {task_spec_snippet}")
    return "\n".join([_PRE_COMPLETION_CHECKLIST, *extra_lines])


def should_inject_pre_completion_checklist(state: TracerState) -> bool:
    if state.get("pre_completion_verified"):
        return False

    messages: list[AnyMessage] = list(state.get("messages", []))
    if not messages:
        return False

    last_message = messages[-1]
    if not isinstance(last_message, AIMessage):
        return False

    has_tool_calls = bool(getattr(last_message, "tool_calls", None))
    return not has_tool_calls


def pre_completion_check_node(state: TracerState) -> dict[str, object]:
    checklist_message = build_pre_completion_checklist_message(state)
    logger.info(
        "Injecting pre-completion verification checklist",
        extra={"run_id": state.get("run_id")},
    )
    return {
        "messages": [SystemMessage(content=checklist_message)],
        "pre_completion_verified": True,
    }


def _format_seconds(seconds: float) -> str:
    if seconds <= 0:
        return "0s"
    minutes, rem_seconds = divmod(int(seconds), 60)
    hours, rem_minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h {rem_minutes}m {rem_seconds}s"
    if minutes > 0:
        return f"{minutes}m {rem_seconds}s"
    return f"{rem_seconds}s"


def build_time_budget_message(state: TracerState, *, now_epoch_seconds: float) -> str:
    run_id = state.get("run_id", "unknown")
    lines = ["Time budget status:", f"- run_id: {run_id}"]

    max_runtime_seconds = state.get("max_runtime_seconds")
    started_at = state.get("run_started_at_epoch_seconds", now_epoch_seconds)
    if max_runtime_seconds is not None:
        elapsed_seconds = max(now_epoch_seconds - started_at, 0.0)
        remaining_runtime_seconds = max(float(max_runtime_seconds) - elapsed_seconds, 0.0)
        lines.append(f"- runtime_remaining: {_format_seconds(remaining_runtime_seconds)}")

    max_steps = state.get("max_steps")
    step_count = state.get("agent_step_count", 0)
    if max_steps is not None:
        remaining_steps = max(max_steps - step_count, 0)
        lines.append(f"- steps_remaining: {remaining_steps}")

    lines.append("- Consider switching to verification and submission if not already in that phase.")
    return "\n".join(lines)


def apply_time_budget_injection(
    state: TracerState,
    *,
    now_epoch_seconds: float | None = None,
) -> tuple[TracerState, SystemMessage | None]:
    now = now_epoch_seconds if now_epoch_seconds is not None else time.time()
    updated_state: TracerState = dict(state)

    if "run_started_at_epoch_seconds" not in updated_state:
        updated_state["run_started_at_epoch_seconds"] = now

    step_count = int(updated_state.get("agent_step_count", 0)) + 1
    updated_state["agent_step_count"] = step_count

    max_steps = updated_state.get("max_steps")
    max_runtime_seconds = updated_state.get("max_runtime_seconds")
    if max_steps is None and max_runtime_seconds is None:
        return updated_state, None

    interval = max(1, int(updated_state.get("time_budget_notice_interval_steps", DEFAULT_TIME_BUDGET_NOTICE_INTERVAL_STEPS)))
    should_inject = step_count % interval == 0

    if max_steps is not None:
        remaining_steps = max_steps - step_count
        if remaining_steps <= 2:
            should_inject = True

    if max_runtime_seconds is not None:
        started_at = updated_state["run_started_at_epoch_seconds"]
        elapsed_seconds = max(now - started_at, 0.0)
        remaining_runtime_seconds = max_runtime_seconds - elapsed_seconds
        if remaining_runtime_seconds <= 120:
            should_inject = True

    if not should_inject or updated_state.get("time_budget_last_notice_step") == step_count:
        return updated_state, None

    updated_state["time_budget_last_notice_step"] = step_count
    message = SystemMessage(content=build_time_budget_message(updated_state, now_epoch_seconds=now))
    logger.info(
        "Injecting tracer time budget context",
        extra={
            "run_id": updated_state.get("run_id"),
            "step_count": step_count,
            "max_steps": max_steps,
            "max_runtime_seconds": max_runtime_seconds,
        },
    )
    return updated_state, message


def _extract_edit_file_paths(message: AIMessage) -> list[str]:
    paths: list[str] = []
    for tool_call in getattr(message, "tool_calls", []) or []:
        if tool_call.get("name") != "edit_file":
            continue
        args = tool_call.get("args", {})
        if not isinstance(args, dict):
            continue
        path = args.get("path")
        if isinstance(path, str) and path.strip():
            paths.append(path)
    return paths


def build_loop_detection_message(*, threshold: int, triggered_paths: list[tuple[str, int]]) -> str:
    lines = [
        "Loop detection notice:",
        (
            "You have edited the same file repeatedly. Reconsider your approach before continuing "
            "to avoid a doom loop."
        ),
        f"- threshold: {threshold}",
    ]
    for path, count in triggered_paths:
        lines.append(f"- file: {path} (edits: {count})")
    return "\n".join(lines)


def apply_loop_detection_injection(
    state: TracerState,
    *,
    response: AIMessage,
) -> tuple[TracerState, SystemMessage | None]:
    updated_state: TracerState = dict(state)
    edit_paths = _extract_edit_file_paths(response)
    if not edit_paths:
        return updated_state, None

    threshold = max(1, int(updated_state.get("loop_detection_threshold", DEFAULT_LOOP_DETECTION_THRESHOLD)))
    edit_counts = dict(updated_state.get("edit_file_counts", {}))
    nudged_files = set(updated_state.get("loop_detection_nudged_files", []))
    triggered_paths: list[tuple[str, int]] = []

    for path in edit_paths:
        next_count = int(edit_counts.get(path, 0)) + 1
        edit_counts[path] = next_count
        if next_count >= threshold and path not in nudged_files:
            triggered_paths.append((path, next_count))
            nudged_files.add(path)

    updated_state["edit_file_counts"] = edit_counts
    updated_state["loop_detection_nudged_files"] = sorted(nudged_files)
    if not triggered_paths:
        return updated_state, None

    message = SystemMessage(
        content=build_loop_detection_message(
            threshold=threshold,
            triggered_paths=triggered_paths,
        )
    )
    logger.info(
        "Injecting loop-detection nudge after repeated file edits",
        extra={
            "run_id": updated_state.get("run_id"),
            "threshold": threshold,
            "triggered_paths": [path for path, _ in triggered_paths],
        },
    )
    return updated_state, message
