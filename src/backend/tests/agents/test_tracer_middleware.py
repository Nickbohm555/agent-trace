from __future__ import annotations

from langchain_core.messages import AIMessage, SystemMessage

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
            "trace_ids": ["trace-1", "trace-2"],
            "current_trace_summary": "Two failing spans in decomposition",
        }
    )

    assert "Pre-completion verification checklist:" in checklist
    assert "run a concrete verification pass against the task spec" in checklist
    assert "run_id: run-verify" in checklist
    assert "trace_ids: trace-1, trace-2" in checklist
    assert "current_trace_summary: Two failing spans in decomposition" in checklist


def test_build_pre_completion_checklist_message_includes_task_spec_when_available() -> None:
    checklist = build_pre_completion_checklist_message(
        {
            "run_id": "run-spec",
            "task_spec_snippet": "Implement endpoint contract exactly as requested.",
        }
    )

    assert "run_id: run-spec" in checklist
    assert "task_spec_snippet: Implement endpoint contract exactly as requested." in checklist


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
