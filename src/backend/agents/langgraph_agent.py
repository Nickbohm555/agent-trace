from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.messages import AIMessage, AnyMessage
from langgraph.graph import END, START, StateGraph

from agents.tracer_state import TracerState

logger = logging.getLogger(__name__)


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


def build_tracer_graph(
    agent_node: Callable[[TracerState], dict[str, list[AnyMessage]]] | None = None,
) -> Any:
    """Build the Section 4 LangGraph skeleton for the tracer deep-agent loop."""
    graph = StateGraph(TracerState)
    graph.add_node("agent", agent_node or default_agent_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "continue": "agent",
            "end": END,
        },
    )
    return graph.compile()
