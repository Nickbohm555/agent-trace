from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from agents.tracer_config import (
    ReasoningLevel,
    ReasoningPhase,
    TracerReasoningConfig,
    resolve_reasoning_level,
    resolve_reasoning_phase,
)
from agents.tracer_state import TracerState
from services.sandbox_service import SandboxService
from services.trace_storage_service import TraceStorageService
from tools.codebase_tools import build_edit_file_tool, build_list_directory_tool, build_read_file_tool
from tools.sandbox_tools import build_run_command_tool
from tools.trace_tools import build_read_trace_tool

logger = logging.getLogger(__name__)

ModelInvoke = Callable[[TracerState, ReasoningPhase, ReasoningLevel], AIMessage]


def should_continue(state: TracerState) -> Literal["continue", "end"]:
    """Route back to the agent loop only when the last AI message has tool calls."""
    messages: list[AnyMessage] = state.get("messages", [])
    if not messages:
        logger.info("Tracer graph ending because no messages are present")
        return "end"

    last_message = messages[-1]
    has_tool_calls = bool(getattr(last_message, "tool_calls", None))
    route = "continue" if has_tool_calls else "end"
    logger.info("Tracer graph conditional route selected", extra={"route": route})
    return route


def default_agent_node(_: TracerState) -> dict[str, list[AIMessage]]:
    """Minimal agent node for section 4 graph backbone; tools are added later."""
    logger.info("Executing default tracer agent node")
    return {"messages": [AIMessage(content="Tracer graph skeleton response.")]}


def default_model_invoke(_: TracerState, __: ReasoningPhase, ___: ReasoningLevel) -> AIMessage:
    """Default model adapter placeholder until tool-bound agent execution is added."""
    return AIMessage(content="Tracer graph skeleton response.")


def build_tracer_graph(
    agent_node: Callable[[TracerState], dict[str, list[AnyMessage]]] | None = None,
    *,
    model_invoke: ModelInvoke | None = None,
    reasoning_config: TracerReasoningConfig | None = None,
    trace_storage_service: TraceStorageService | None = None,
    sandbox_service: SandboxService | None = None,
    tools: list[BaseTool] | None = None,
) -> Any:
    """Build the Section 4 LangGraph skeleton for the tracer deep-agent loop."""
    resolved_tools = list(tools or [])
    if trace_storage_service is not None:
        resolved_tools.append(build_read_trace_tool(trace_storage_service))
    if sandbox_service is not None:
        resolved_tools.append(build_list_directory_tool(sandbox_service))
        resolved_tools.append(build_read_file_tool(sandbox_service))
        resolved_tools.append(build_edit_file_tool(sandbox_service))
        resolved_tools.append(build_run_command_tool(sandbox_service))

    if agent_node is None:
        selected_reasoning_config = reasoning_config or TracerReasoningConfig()
        selected_model_invoke = model_invoke or default_model_invoke

        def configured_agent_node(state: TracerState) -> dict[str, list[AnyMessage]]:
            phase = resolve_reasoning_phase(state.get("reasoning_phase"))
            level = resolve_reasoning_level(
                state.get("reasoning_level"),
                fallback=selected_reasoning_config.level_for_phase(phase),
            )
            logger.info(
                "Executing tracer agent with reasoning configuration",
                extra={"phase": phase, "reasoning_level": level, "run_id": state.get("run_id")},
            )
            return {"messages": [selected_model_invoke(state, phase, level)]}

        resolved_agent_node = configured_agent_node
    else:
        resolved_agent_node = agent_node

    graph = StateGraph(TracerState)
    graph.add_node("agent", resolved_agent_node)
    if resolved_tools:
        graph.add_node("tools", ToolNode(resolved_tools))

    graph.add_edge(START, "agent")
    if resolved_tools:
        graph.add_conditional_edges(
            "agent",
            should_continue,
            {
                "continue": "tools",
                "end": END,
            },
        )
        graph.add_edge("tools", "agent")
    else:
        graph.add_conditional_edges(
            "agent",
            should_continue,
            {
                "continue": "agent",
                "end": END,
            },
        )
    return graph.compile()
