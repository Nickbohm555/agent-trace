from __future__ import annotations

from langchain_core.messages import AIMessage

from agents.langgraph_agent import build_tracer_graph, should_continue


def test_should_continue_routes_continue_when_tool_calls_present() -> None:
    route = should_continue(
        {
            "messages": [
                AIMessage(
                    content="Need tool output",
                    tool_calls=[{"name": "read_trace", "args": {"run_id": "run-1"}, "id": "tc-1"}],
                )
            ]
        }
    )

    assert route == "continue"


def test_build_tracer_graph_default_agent_runs_single_step_and_ends() -> None:
    graph = build_tracer_graph()

    result = graph.invoke({"messages": [], "run_id": "run-123", "current_trace_summary": None})

    assert "messages" in result
    assert len(result["messages"]) == 1
    assert result["messages"][0].content == "Tracer graph skeleton response."
