from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool

from agents.langgraph_agent import build_tracer_graph, should_continue
from agents.tracer_config import TracerReasoningConfig
from schemas.sandbox import SandboxCreateRequest
from services.sandbox_service import SandboxService


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


def test_should_continue_routes_verify_before_end_when_not_yet_verified() -> None:
    route = should_continue({"messages": [AIMessage(content="All done")]})

    assert route == "verify"


def test_build_tracer_graph_default_agent_runs_single_step_and_ends() -> None:
    graph = build_tracer_graph()

    result = graph.invoke(
        {
            "messages": [],
            "run_id": "run-123",
            "current_trace_summary": None,
            "pre_completion_verified": True,
        }
    )

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
            "pre_completion_verified": True,
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
            "pre_completion_verified": True,
        }
    )

    assert captures == [("planning", "medium")]


def test_build_tracer_graph_injects_tracer_system_prompt_for_model_adapter() -> None:
    captured_first_message: SystemMessage | None = None

    def model_invoke(state: dict[str, object], _: str, __: str) -> AIMessage:
        nonlocal captured_first_message
        first_message = state["messages"][0]
        assert isinstance(first_message, SystemMessage)
        captured_first_message = first_message
        return AIMessage(content="System prompt acknowledged")

    graph = build_tracer_graph(model_invoke=model_invoke)
    result = graph.invoke(
        {
            "messages": [],
            "run_id": "run-prompt",
            "current_trace_summary": None,
            "pre_completion_verified": True,
        }
    )

    assert captured_first_message is not None
    assert "Planning & Discovery phase" in captured_first_message.content
    assert "Build phase" in captured_first_message.content
    assert "Verify phase" in captured_first_message.content
    assert "Fix phase" in captured_first_message.content
    assert result["messages"][0].content == "System prompt acknowledged"


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
    result = graph.invoke(
        {
            "messages": [],
            "run_id": "run-with-error",
            "current_trace_summary": None,
            "pre_completion_verified": True,
        }
    )

    assert call_count == 2
    assert len(result["messages"]) == 3
    assert isinstance(result["messages"][1], ToolMessage)
    assert "boom" in str(result["messages"][1].content)
    assert result["messages"][2].content == "Trace analyzed"


def _mock_clone_to_local_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_clone(*, target_repo_url: str, repo_path: Path) -> None:
        repo_path.mkdir(parents=True, exist_ok=True)
        (repo_path / "README.md").write_text(
            f"cloned from {target_repo_url}\n",
            encoding="utf-8",
        )
        (repo_path / "src").mkdir(parents=True, exist_ok=True)
        (repo_path / "src" / "app.py").write_text("print('sandbox')\n", encoding="utf-8")

    monkeypatch.setattr(SandboxService, "_clone_repo", staticmethod(fake_clone))


def test_build_tracer_graph_executes_codebase_tools_with_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_clone_to_local_repo(monkeypatch)
    sandbox_service = SandboxService(default_target_repo_url="https://example.com/default.git")
    session = sandbox_service.create_sandbox(SandboxCreateRequest())

    call_count = 0

    def model_invoke(state: dict[str, object], _: str, __: str) -> AIMessage:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return AIMessage(
                content="List root",
                tool_calls=[
                    {
                        "name": "list_directory",
                        "args": {"sandbox_path": session.sandbox_path, "path": "."},
                        "id": "tc-list",
                    }
                ],
            )
        if call_count == 2:
            assert isinstance(state["messages"][-1], ToolMessage)
            return AIMessage(
                content="Edit app file",
                tool_calls=[
                    {
                        "name": "edit_file",
                        "args": {
                            "sandbox_path": session.sandbox_path,
                            "path": "src/app.py",
                            "content": "print('updated sandbox')\n",
                        },
                        "id": "tc-edit",
                    }
                ],
            )
        if call_count == 3:
            assert isinstance(state["messages"][-1], ToolMessage)
            return AIMessage(
                content="Read app file",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"sandbox_path": session.sandbox_path, "path": "src/app.py"},
                        "id": "tc-read",
                    }
                ],
            )

        assert isinstance(state["messages"][-1], ToolMessage)
        return AIMessage(content="Codebase inspected")

    graph = build_tracer_graph(model_invoke=model_invoke, sandbox_service=sandbox_service)
    result = graph.invoke(
        {
            "messages": [],
            "run_id": "run-codebase",
            "current_trace_summary": None,
            "pre_completion_verified": True,
        }
    )

    assert call_count == 4
    assert len(result["messages"]) == 7
    assert isinstance(result["messages"][1], ToolMessage)
    assert "README.md" in str(result["messages"][1].content)
    assert isinstance(result["messages"][3], ToolMessage)
    assert "updated" in str(result["messages"][3].content)
    assert isinstance(result["messages"][5], ToolMessage)
    assert "print('updated sandbox')" in str(result["messages"][5].content)
    assert result["messages"][6].content == "Codebase inspected"

    sandbox_service.teardown_sandbox(session)


def test_build_tracer_graph_executes_run_command_tool_with_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_clone_to_local_repo(monkeypatch)
    sandbox_service = SandboxService(default_target_repo_url="https://example.com/default.git")
    session = sandbox_service.create_sandbox(SandboxCreateRequest())

    call_count = 0

    def model_invoke(state: dict[str, object], _: str, __: str) -> AIMessage:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return AIMessage(
                content="Run command in sandbox",
                tool_calls=[
                    {
                        "name": "run_command",
                        "args": {
                            "sandbox_path": session.sandbox_path,
                            "command": ["sh", "-c", "echo graph-run-command"],
                            "timeout_seconds": 10,
                        },
                        "id": "tc-run-command",
                    }
                ],
            )

        assert isinstance(state["messages"][-1], ToolMessage)
        return AIMessage(content="Command verified")

    graph = build_tracer_graph(model_invoke=model_invoke, sandbox_service=sandbox_service)
    result = graph.invoke(
        {
            "messages": [],
            "run_id": "run-command",
            "current_trace_summary": None,
            "pre_completion_verified": True,
        }
    )

    assert call_count == 2
    assert len(result["messages"]) == 3
    assert isinstance(result["messages"][1], ToolMessage)
    assert "graph-run-command" in str(result["messages"][1].content)
    assert '"exit_code": 0' in str(result["messages"][1].content)
    assert result["messages"][2].content == "Command verified"

    sandbox_service.teardown_sandbox(session)


def test_build_tracer_graph_injects_local_context_on_first_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_clone_to_local_repo(monkeypatch)
    sandbox_service = SandboxService(default_target_repo_url="https://example.com/default.git")
    session = sandbox_service.create_sandbox(SandboxCreateRequest())

    captured_messages: list[object] = []

    def model_invoke(state: dict[str, object], _: str, __: str) -> AIMessage:
        nonlocal captured_messages
        captured_messages = list(state["messages"])
        return AIMessage(content="Local context captured")

    graph = build_tracer_graph(model_invoke=model_invoke, sandbox_service=sandbox_service)
    result = graph.invoke(
        {
            "messages": [],
            "run_id": "run-local-context",
            "current_trace_summary": None,
            "sandbox_path": session.sandbox_path,
            "pre_completion_verified": True,
        }
    )

    assert isinstance(captured_messages[0], SystemMessage)
    assert "Planning & Discovery phase" in str(captured_messages[0].content)
    assert isinstance(captured_messages[1], SystemMessage)
    assert "Sandbox local context:" in str(captured_messages[1].content)
    assert "tool_paths:" in str(captured_messages[1].content)
    assert result["messages"][0].content == "Local context captured"
    assert "Sandbox local context:" in str(result["local_context"])

    sandbox_service.teardown_sandbox(session)


def test_build_tracer_graph_injects_time_budget_message_with_short_budget() -> None:
    saw_time_budget_context = False

    def model_invoke(state: dict[str, object], _: str, __: str) -> AIMessage:
        nonlocal saw_time_budget_context
        saw_time_budget_context = any(
            isinstance(message, SystemMessage) and "Time budget status:" in str(message.content)
            for message in state["messages"]
        )
        return AIMessage(content="Budget acknowledged")

    graph = build_tracer_graph(model_invoke=model_invoke)
    result = graph.invoke(
        {
            "messages": [],
            "run_id": "run-time-budget",
            "current_trace_summary": None,
            "max_steps": 1,
            "pre_completion_verified": True,
        }
    )

    assert saw_time_budget_context is True
    assert any(
        isinstance(message, SystemMessage) and "Time budget status:" in str(message.content)
        for message in result["messages"]
    )
    assert result["agent_step_count"] == 1
    assert result["messages"][-1].content == "Budget acknowledged"
