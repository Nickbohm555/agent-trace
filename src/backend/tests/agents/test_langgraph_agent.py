from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import StructuredTool

from agents.langgraph_agent import build_tracer_graph, should_continue
from agents.tracer_config import TracerReasoningConfig


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


def test_build_tracer_graph_passes_phase_budget_to_model_adapter() -> None:
    captures: list[tuple[str, str]] = []

    def model_invoke(_: dict[str, object], phase: str, level: str) -> AIMessage:
        captures.append((phase, level))
        return AIMessage(content=f"phase={phase};level={level}")

    graph = build_tracer_graph(
        model_invoke=model_invoke,
        reasoning_config=TracerReasoningConfig(
            default_level="medium",
            phase_levels={
                "planning": "xhigh",
                "implementation": "low",
                "verification": "high",
            },
        ),
    )

    result = graph.invoke(
        {
            "messages": [],
            "run_id": "run-456",
            "current_trace_summary": None,
            "reasoning_phase": "implementation",
        }
    )

    assert captures == [("implementation", "low")]
    assert result["messages"][0].content == "phase=implementation;level=low"


def test_build_tracer_graph_state_level_override_wins_over_phase_defaults() -> None:
    captures: list[tuple[str, str]] = []

    def model_invoke(_: dict[str, object], phase: str, level: str) -> AIMessage:
        captures.append((phase, level))
        return AIMessage(content=f"phase={phase};level={level}")

    graph = build_tracer_graph(model_invoke=model_invoke)

    graph.invoke(
        {
            "messages": [],
            "run_id": "run-789",
            "current_trace_summary": None,
            "reasoning_phase": "planning",
            "reasoning_level": "medium",
        }
    )

    assert captures == [("planning", "medium")]


def test_build_tracer_graph_executes_tool_node_when_tool_calls_present() -> None:
    tool = StructuredTool.from_function(
        name="read_trace",
        description="Return a synthetic trace summary for testing.",
        func=lambda run_id: {"run_id": run_id, "errors": [{"message": "boom"}]},
    )

    call_count = 0

    def model_invoke(state: dict[str, object], _: str, __: str) -> AIMessage:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return AIMessage(
                content="Need trace details",
                tool_calls=[
                    {
                        "name": "read_trace",
                        "args": {"run_id": "run-with-error"},
                        "id": "tc-read-trace",
                    }
                ],
            )

        assert isinstance(state["messages"][-1], ToolMessage)
        return AIMessage(content="Trace analyzed")

    graph = build_tracer_graph(model_invoke=model_invoke, tools=[tool])
    result = graph.invoke({"messages": [], "run_id": "run-with-error", "current_trace_summary": None})

    assert call_count == 2
    assert len(result["messages"]) == 3
    assert isinstance(result["messages"][1], ToolMessage)
    assert "boom" in str(result["messages"][1].content)
    assert result["messages"][2].content == "Trace analyzed"
