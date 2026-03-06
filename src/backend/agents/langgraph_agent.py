from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.messages import AIMessage, AnyMessage, SystemMessage
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
from agents.tracer_context import build_local_context_message, contains_local_context_message
from agents.tracer_middleware import (
    pre_completion_check_node,
    should_inject_pre_completion_checklist,
)
from agents.tracer_prompts import build_tracer_system_prompt
from agents.tracer_state import TracerState
from services.sandbox_service import SandboxService
from services.trace_storage_service import TraceStorageService
from tools.codebase_tools import build_edit_file_tool, build_list_directory_tool, build_read_file_tool
from tools.sandbox_tools import build_run_command_tool
from tools.trace_tools import build_read_trace_tool

logger = logging.getLogger(__name__)

ModelInvoke = Callable[[TracerState, ReasoningPhase, ReasoningLevel], AIMessage]


def should_continue(state: TracerState) -> Literal["continue", "verify", "end"]:
    """Route to tools, verification middleware, or end based on latest model output."""
    messages: list[AnyMessage] = state.get("messages", [])
    if not messages:
        logger.info("Tracer graph ending because no messages are present")
        return "end"

    last_message = messages[-1]
    has_tool_calls = bool(getattr(last_message, "tool_calls", None))
    if has_tool_calls:
        route = "continue"
    elif should_inject_pre_completion_checklist(state):
        route = "verify"
    else:
        route = "end"
    logger.info("Tracer graph conditional route selected", extra={"route": route})
    return route


def default_agent_node(_: TracerState) -> dict[str, list[AIMessage]]:
    """Minimal agent node for section 4 graph backbone; tools are added later."""
    logger.info("Executing default tracer agent node")
    return {"messages": [AIMessage(content="Tracer graph skeleton response.")]}


def default_model_invoke(_: TracerState, __: ReasoningPhase, ___: ReasoningLevel) -> AIMessage:
    """Default model adapter placeholder until tool-bound agent execution is added."""
    return AIMessage(content="Tracer graph skeleton response.")


def _inject_system_prompt(state: TracerState, system_prompt: str) -> TracerState:
    messages: list[AnyMessage] = list(state.get("messages", []))
    if messages and isinstance(messages[0], SystemMessage) and system_prompt in str(messages[0].content):
        return state

    prompted_state: TracerState = dict(state)
    prompted_state["messages"] = [SystemMessage(content=system_prompt), *messages]
    return prompted_state


def _inject_local_context(
    state: TracerState,
    *,
    sandbox_service: SandboxService | None,
) -> TracerState:
    if sandbox_service is None:
        return state

    sandbox_path = state.get("sandbox_path")
    if not sandbox_path:
        return state

    messages: list[AnyMessage] = list(state.get("messages", []))
    if contains_local_context_message(messages):
        return state

    context_message = state.get("local_context")
    if not context_message:
        context_message = build_local_context_message(
            sandbox_service=sandbox_service,
            sandbox_path=sandbox_path,
        )

    contextual_state: TracerState = dict(state)
    contextual_state["local_context"] = context_message
    contextual_state["messages"] = [SystemMessage(content=context_message), *messages]
    logger.info(
        "Injected tracer local context",
        extra={"sandbox_path": sandbox_path, "run_id": state.get("run_id")},
    )
    return contextual_state


def build_tracer_graph(
    agent_node: Callable[[TracerState], dict[str, list[AnyMessage]]] | None = None,
    *,
    model_invoke: ModelInvoke | None = None,
    reasoning_config: TracerReasoningConfig | None = None,
    trace_storage_service: TraceStorageService | None = None,
    sandbox_service: SandboxService | None = None,
    tools: list[BaseTool] | None = None,
    system_prompt: str | None = None,
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
        selected_system_prompt = system_prompt or build_tracer_system_prompt()

        def configured_agent_node(state: TracerState) -> dict[str, list[AnyMessage]]:
            phase = resolve_reasoning_phase(state.get("reasoning_phase"))
            level = resolve_reasoning_level(
                state.get("reasoning_level"),
                fallback=selected_reasoning_config.level_for_phase(phase),
            )
            contextual_state = _inject_local_context(state, sandbox_service=sandbox_service)
            prompted_state = _inject_system_prompt(contextual_state, selected_system_prompt)
            logger.info(
                "Executing tracer agent with reasoning configuration",
                extra={"phase": phase, "reasoning_level": level, "run_id": state.get("run_id")},
            )
            response = selected_model_invoke(prompted_state, phase, level)
            updates: dict[str, Any] = {"messages": [response]}
            if contextual_state.get("local_context") and not state.get("local_context"):
                updates["local_context"] = contextual_state["local_context"]
            return updates

        resolved_agent_node = configured_agent_node
    else:
        resolved_agent_node = agent_node

    graph = StateGraph(TracerState)
    graph.add_node("agent", resolved_agent_node)
    graph.add_node("pre_completion_check", pre_completion_check_node)
    if resolved_tools:
        graph.add_node("tools", ToolNode(resolved_tools))

    graph.add_edge(START, "agent")
    if resolved_tools:
        graph.add_conditional_edges(
            "agent",
            should_continue,
            {
                "continue": "tools",
                "verify": "pre_completion_check",
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
                "verify": "pre_completion_check",
                "end": END,
            },
        )
    graph.add_edge("pre_completion_check", "agent")
    return graph.compile()
