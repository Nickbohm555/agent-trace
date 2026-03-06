from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, AnyMessage, SystemMessage

from agents.tracer_state import TracerState

logger = logging.getLogger(__name__)

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
    extra_lines = [f"- run_id: {run_id}"]
    if trace_summary:
        extra_lines.append(f"- current_trace_summary: {trace_summary}")
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
