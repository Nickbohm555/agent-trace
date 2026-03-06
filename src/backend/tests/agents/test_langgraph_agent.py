from __future__ import annotations

from langchain_core.messages import AIMessage

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
