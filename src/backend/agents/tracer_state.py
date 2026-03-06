from __future__ import annotations

from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from agents.tracer_config import ReasoningLevel, ReasoningPhase


class TracerState(TypedDict, total=False):
    """Shared state for the tracer deep-agent graph skeleton."""

    messages: Annotated[list[AnyMessage], add_messages]
    current_trace_summary: str | None
    run_id: str
    sandbox_path: str
    local_context: str
    reasoning_phase: ReasoningPhase
    reasoning_level: ReasoningLevel
    reasoning_phase_levels: dict[ReasoningPhase, ReasoningLevel]
    pre_completion_verified: bool
