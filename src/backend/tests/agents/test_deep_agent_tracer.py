from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents import deep_agent_tracer
from agents.deep_agent_tracer import build_deep_agent_tracer
from schemas.sandbox import SandboxCreateRequest
from services.sandbox_service import SandboxService


def _patch_bind_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(FakeMessagesListChatModel, "bind_tools", lambda self, *_args, **_kwargs: self)


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


def test_build_deep_agent_tracer_invokes_with_messages_state(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_bind_tools(monkeypatch)
    graph = build_deep_agent_tracer(
        model=FakeMessagesListChatModel(
            responses=[AIMessage(content="Minimal deep-agent tracer response.")],
        )
    )

    result = graph.invoke({"messages": [HumanMessage(content="Analyze this trace")]})

    assert "messages" in result
    assert len(result["messages"]) >= 2
    assert result["messages"][-1].content == "Minimal deep-agent tracer response."


def test_build_deep_agent_tracer_propagates_tracer_state_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_bind_tools(monkeypatch)
    graph = build_deep_agent_tracer(
        model=FakeMessagesListChatModel(
            responses=[AIMessage(content="State propagation response.")],
        )
    )

    initial_state = {
        "messages": [HumanMessage(content="Analyze this trace with extended state.")],
        "run_id": "run-state-1",
        "sandbox_path": "/tmp/sandbox-state-1",
        "local_context": "Sandbox local context: mocked.",
        "pre_completion_verified": False,
        "agent_step_count": 1,
        "time_budget_last_notice_step": 0,
        "loop_detection_nudged_files": ["src/main.py"],
        "parallel_error_findings": [{"trace_id": "trace-1", "summary": "failing test"}],
        "harness_change_set": {"run_id": "run-state-1", "harness_changes": []},
    }

    result = graph.invoke(initial_state)

    assert result["run_id"] == "run-state-1"
    assert result["sandbox_path"] == "/tmp/sandbox-state-1"
    assert result["local_context"] == "Sandbox local context: mocked."
    assert result["pre_completion_verified"] is False
    assert result["agent_step_count"] == 1
    assert result["time_budget_last_notice_step"] == 0
    assert result["loop_detection_nudged_files"] == ["src/main.py"]
    assert result["parallel_error_findings"] == [{"trace_id": "trace-1", "summary": "failing test"}]
    assert result["harness_change_set"] == {"run_id": "run-state-1", "harness_changes": []}


def test_build_deep_agent_tracer_uses_tracer_system_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_deep_agent(*_args, **kwargs):
        captured.update(kwargs)
        return "compiled-graph"

    monkeypatch.setattr(deep_agent_tracer, "create_deep_agent", fake_create_deep_agent)

    result = build_deep_agent_tracer()

    assert result == "compiled-graph"
    assert "Planning & Discovery phase" in str(captured["system_prompt"])
    assert "Build phase" in str(captured["system_prompt"])
    assert "Verify phase" in str(captured["system_prompt"])
    assert "Fix phase" in str(captured["system_prompt"])


def test_build_deep_agent_tracer_registers_tracer_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_deep_agent(*_args, **kwargs):
        captured.update(kwargs)
        return "compiled-graph"

    monkeypatch.setattr(deep_agent_tracer, "create_deep_agent", fake_create_deep_agent)

    class FakeTraceStorageService:
        def load_traces(self, *_args, **_kwargs):  # pragma: no cover
            return []

    graph = build_deep_agent_tracer(
        trace_storage_service=FakeTraceStorageService(),
        sandbox_service=SandboxService(default_target_repo_url="https://example.com/default.git"),
    )

    assert graph == "compiled-graph"
    tool_names = [tool.name for tool in captured["tools"]]
    assert tool_names == [
        "read_trace",
        "list_directory",
        "read_file",
        "edit_file",
        "run_command",
    ]


def test_build_deep_agent_tracer_executes_list_directory_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_bind_tools(monkeypatch)
    _mock_clone_to_local_repo(monkeypatch)
    sandbox_service = SandboxService(default_target_repo_url="https://example.com/default.git")
    session = sandbox_service.create_sandbox(SandboxCreateRequest())

    graph = build_deep_agent_tracer(
        model=FakeMessagesListChatModel(
            responses=[
                AIMessage(
                    content="List sandbox root",
                    tool_calls=[
                        {
                            "name": "list_directory",
                            "args": {"sandbox_path": session.sandbox_path, "path": "."},
                            "id": "tc-list-root",
                        }
                    ],
                ),
                AIMessage(content="Directory checked."),
            ],
        ),
        sandbox_service=sandbox_service,
    )

    result = graph.invoke(
        {
            "messages": [HumanMessage(content="Inspect files")],
            "sandbox_path": session.sandbox_path,
        }
    )

    assert any(isinstance(message, ToolMessage) for message in result["messages"])
    assert "README.md" in str(result["messages"][-2].content)
    assert result["messages"][-1].content == "Directory checked."

    sandbox_service.teardown_sandbox(session)


def test_build_deep_agent_tracer_overrides_model_sandbox_path_with_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_bind_tools(monkeypatch)
    _mock_clone_to_local_repo(monkeypatch)
    sandbox_service = SandboxService(default_target_repo_url="https://example.com/default.git")
    active_session = sandbox_service.create_sandbox(
        SandboxCreateRequest(target_repo_url="https://example.com/active.git")
    )
    other_session = sandbox_service.create_sandbox(
        SandboxCreateRequest(target_repo_url="https://example.com/other.git")
    )

    graph = build_deep_agent_tracer(
        model=FakeMessagesListChatModel(
            responses=[
                AIMessage(
                    content="Read README from wrong sandbox",
                    tool_calls=[
                        {
                            "name": "read_file",
                            "args": {
                                "sandbox_path": other_session.sandbox_path,
                                "path": "README.md",
                            },
                            "id": "tc-readme",
                        }
                    ],
                ),
                AIMessage(content="Read completed."),
            ],
        ),
        sandbox_service=sandbox_service,
    )

    result = graph.invoke(
        {
            "messages": [HumanMessage(content="Inspect README in the active sandbox.")],
            "sandbox_path": active_session.sandbox_path,
        }
    )

    assert "https://example.com/active.git" in str(result["messages"][-2].content)
    assert "https://example.com/other.git" not in str(result["messages"][-2].content)
    assert result["messages"][-1].content == "Read completed."

    sandbox_service.teardown_sandbox(active_session)
    sandbox_service.teardown_sandbox(other_session)


def test_build_deep_agent_tracer_injects_local_context_on_first_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_bind_tools(monkeypatch)
    _mock_clone_to_local_repo(monkeypatch)
    captured_messages: list[list[object]] = []
    original_generate = FakeMessagesListChatModel._generate

    def recording_generate(self, messages, stop=None, run_manager=None, **kwargs):
        captured_messages.append(list(messages))
        return original_generate(self, messages, stop=stop, run_manager=run_manager, **kwargs)

    monkeypatch.setattr(FakeMessagesListChatModel, "_generate", recording_generate)
    sandbox_service = SandboxService(default_target_repo_url="https://example.com/default.git")
    session = sandbox_service.create_sandbox(SandboxCreateRequest())

    model = FakeMessagesListChatModel(
        responses=[AIMessage(content="Local context acknowledged.")],
    )
    graph = build_deep_agent_tracer(
        model=model,
        sandbox_service=sandbox_service,
    )

    result = graph.invoke(
        {
            "messages": [HumanMessage(content="Inspect files")],
            "sandbox_path": session.sandbox_path,
        }
    )

    assert captured_messages
    first_call_messages = captured_messages[0]
    assert "Sandbox local context:" in "\n".join(str(message.content) for message in first_call_messages)
    assert "tool_paths:" in "\n".join(str(message.content) for message in first_call_messages)
    assert "Sandbox local context:" in str(result["local_context"])
    assert result["messages"][-1].content == "Local context acknowledged."

    sandbox_service.teardown_sandbox(session)


def test_build_deep_agent_tracer_blocks_sandbox_tool_without_state_sandbox_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_bind_tools(monkeypatch)
    _mock_clone_to_local_repo(monkeypatch)
    sandbox_service = SandboxService(default_target_repo_url="https://example.com/default.git")
    session = sandbox_service.create_sandbox(SandboxCreateRequest())

    graph = build_deep_agent_tracer(
        model=FakeMessagesListChatModel(
            responses=[
                AIMessage(
                    content="List files without sandbox state",
                    tool_calls=[
                        {
                            "name": "list_directory",
                            "args": {"sandbox_path": session.sandbox_path, "path": "."},
                            "id": "tc-list-no-state",
                        }
                    ],
                )
            ],
        ),
        sandbox_service=sandbox_service,
    )

    with pytest.raises(ValueError, match="sandbox_path is required"):
        graph.invoke({"messages": [HumanMessage(content="Inspect files")]})

    sandbox_service.teardown_sandbox(session)
