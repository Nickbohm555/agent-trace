from __future__ import annotations

from langchain_core.messages import AIMessage, SystemMessage

from agents.langgraph_agent import build_tracer_graph
from agents.tracer_middleware import (
    apply_loop_detection_injection,
    apply_time_budget_injection,
    build_loop_detection_message,
    build_time_budget_message,
    build_pre_completion_checklist_message,
    should_inject_pre_completion_checklist,
)


def test_should_inject_pre_completion_checklist_only_before_verification() -> None:
    assert should_inject_pre_completion_checklist({"messages": [AIMessage(content="Done")]})
    assert not should_inject_pre_completion_checklist(
        {
            "messages": [AIMessage(content="Done")],
            "pre_completion_verified": True,
        }
    )


def test_build_pre_completion_checklist_message_contains_expected_content() -> None:
    checklist = build_pre_completion_checklist_message(
        {
            "run_id": "run-verify",
            "current_trace_summary": "Two failing spans in decomposition",
        }
    )

    assert "Pre-completion verification checklist:" in checklist
    assert "run a concrete verification pass against the task spec" in checklist
    assert "run_id: run-verify" in checklist
    assert "current_trace_summary: Two failing spans in decomposition" in checklist


def test_build_tracer_graph_forces_one_more_turn_for_verification_before_end() -> None:
    call_count = 0

    def model_invoke(state: dict[str, object], _: str, __: str) -> AIMessage:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return AIMessage(content="Implementation complete.")

        assert isinstance(state["messages"][-1], SystemMessage)
        assert "Pre-completion verification checklist:" in str(state["messages"][-1].content)
        return AIMessage(content="Verified via tests and ready to submit.")

    graph = build_tracer_graph(model_invoke=model_invoke)
    result = graph.invoke({"messages": [], "run_id": "run-verify-loop", "current_trace_summary": None})

    assert call_count == 2
    assert len(result["messages"]) == 3
    assert result["messages"][0].content == "Implementation complete."
    assert "Pre-completion verification checklist:" in str(result["messages"][1].content)
    assert result["messages"][2].content == "Verified via tests and ready to submit."
    assert result["pre_completion_verified"] is True


def test_apply_time_budget_injection_emits_message_for_short_step_budget() -> None:
    updated_state, message = apply_time_budget_injection(
        {
            "run_id": "run-budget",
            "messages": [],
            "max_steps": 1,
        },
        now_epoch_seconds=1000.0,
    )

    assert updated_state["agent_step_count"] == 1
    assert updated_state["run_started_at_epoch_seconds"] == 1000.0
    assert message is not None
    assert "Time budget status:" in str(message.content)
    assert "steps_remaining: 0" in str(message.content)


def test_build_time_budget_message_contains_runtime_and_step_remaining() -> None:
    message = build_time_budget_message(
        {
            "run_id": "run-budget",
            "max_runtime_seconds": 120,
            "run_started_at_epoch_seconds": 100.0,
            "max_steps": 10,
            "agent_step_count": 4,
        },
        now_epoch_seconds=130.0,
    )

    assert "Time budget status:" in message
    assert "runtime_remaining: 1m 30s" in message
    assert "steps_remaining: 6" in message


def test_apply_loop_detection_injection_emits_nudge_after_threshold() -> None:
    updated_state, message = apply_loop_detection_injection(
        {
            "run_id": "run-loop",
            "edit_file_counts": {"src/app.py": 1},
            "loop_detection_threshold": 2,
        },
        response=AIMessage(
            content="Apply fix",
            tool_calls=[
                {
                    "name": "edit_file",
                    "args": {"sandbox_path": "/tmp/sb", "path": "src/app.py", "content": "next"},
                    "id": "tc-edit-1",
                }
            ],
        ),
    )

    assert updated_state["edit_file_counts"]["src/app.py"] == 2
    assert message is not None
    assert "Loop detection notice:" in str(message.content)
    assert "file: src/app.py (edits: 2)" in str(message.content)


def test_build_loop_detection_message_includes_threshold_and_paths() -> None:
    message = build_loop_detection_message(
        threshold=5,
        triggered_paths=[("src/main.py", 5), ("src/util.py", 7)],
    )

    assert "threshold: 5" in message
    assert "file: src/main.py (edits: 5)" in message
    assert "file: src/util.py (edits: 7)" in message
