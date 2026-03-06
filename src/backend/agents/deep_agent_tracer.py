from __future__ import annotations

import logging
from typing import Any, get_type_hints

from deepagents import create_deep_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt.tool_node import ToolCallRequest

from agents.tracer_context import build_local_context_message, contains_local_context_message
from agents.tracer_prompts import build_tracer_system_prompt
from agents.tracer_state import TracerState
from services.sandbox_service import SandboxService
from services.trace_storage_service import TraceStorageService
from tools.codebase_tools import build_edit_file_tool, build_list_directory_tool, build_read_file_tool
from tools.sandbox_tools import build_run_command_tool
from tools.trace_tools import build_read_trace_tool

logger = logging.getLogger(__name__)
_SANDBOX_TOOL_NAMES = {"list_directory", "read_file", "edit_file", "run_command"}
_TRACER_STATE_FIELDS = sorted(get_type_hints(TracerState).keys())


class TracerStateSchemaMiddleware(AgentMiddleware[TracerState, Any, Any]):
    """Register tracer-specific state keys on the deep-agent graph."""

    state_schema = TracerState


class TracerSandboxScopeMiddleware(AgentMiddleware[TracerState, Any, Any]):
    """Force sandbox tools to use the active tracer sandbox_path from graph state."""

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Any,
    ) -> ToolMessage | Any:
        tool_name = request.tool_call.get("name")
        if tool_name not in _SANDBOX_TOOL_NAMES:
            return handler(request)

        state = request.state if isinstance(request.state, dict) else {}
        active_sandbox_path = state.get("sandbox_path")
        if not active_sandbox_path:
            logger.warning(
                "Blocking sandbox tool call because tracer state is missing sandbox_path",
                extra={"tool_name": tool_name},
            )
            raise ValueError("sandbox_path is required in tracer state for sandbox tool execution")

        existing_args = request.tool_call.get("args")
        if isinstance(existing_args, dict):
            args = dict(existing_args)
        else:
            args = {}

        provided_sandbox_path = args.get("sandbox_path")
        args["sandbox_path"] = active_sandbox_path
        if provided_sandbox_path and provided_sandbox_path != active_sandbox_path:
            logger.info(
                "Overriding model-provided sandbox_path for sandbox tool call",
                extra={
                    "tool_name": tool_name,
                    "provided_sandbox_path": provided_sandbox_path,
                    "active_sandbox_path": active_sandbox_path,
                },
            )
        else:
            logger.info(
                "Applying active sandbox_path to sandbox tool call",
                extra={
                    "tool_name": tool_name,
                    "active_sandbox_path": active_sandbox_path,
                },
            )

        return handler(
            request.override(
                tool_call={
                    **request.tool_call,
                    "args": args,
                }
            )
        )


class TracerLocalContextMiddleware(AgentMiddleware[TracerState, Any, Any]):
    """Inject sandbox local context into deep-agent state before the first model turn."""

    def __init__(self, *, sandbox_service: SandboxService | None) -> None:
        self._sandbox_service = sandbox_service

    def before_agent(self, state: TracerState, runtime: Any) -> dict[str, Any] | None:
        del runtime
        if self._sandbox_service is None:
            return None

        sandbox_path = state.get("sandbox_path")
        if not sandbox_path:
            return None

        messages = list(state.get("messages", []))
        if contains_local_context_message(messages):
            return None

        context_message = state.get("local_context")
        if not context_message:
            context_message = build_local_context_message(
                sandbox_service=self._sandbox_service,
                sandbox_path=sandbox_path,
            )

        logger.info(
            "Injected tracer local context into deep-agent state",
            extra={"sandbox_path": sandbox_path, "run_id": state.get("run_id")},
        )
        return {
            "local_context": context_message,
            "messages": [SystemMessage(content=context_message), *messages],
        }


def _build_tracer_tools(
    *,
    trace_storage_service: TraceStorageService | None,
    sandbox_service: SandboxService | None,
) -> list[BaseTool]:
    tools: list[BaseTool] = []
    if trace_storage_service is not None:
        tools.append(build_read_trace_tool(trace_storage_service))
    if sandbox_service is not None:
        tools.extend(
            [
                build_list_directory_tool(sandbox_service),
                build_read_file_tool(sandbox_service),
                build_edit_file_tool(sandbox_service),
                build_run_command_tool(sandbox_service),
            ]
        )
    logger.info(
        "Resolved deep-agent tracer tools",
        extra={
            "tool_names": [tool.name for tool in tools],
            "trace_storage_configured": trace_storage_service is not None,
            "sandbox_configured": sandbox_service is not None,
        },
    )
    return tools


def build_deep_agent_tracer(
    *,
    model: str | BaseChatModel | None = None,
    system_prompt: str | None = None,
    trace_storage_service: TraceStorageService | None = None,
    sandbox_service: SandboxService | None = None,
) -> Any:
    """Build a deep-agent tracer graph with tracer state and sandbox-scoped tools."""
    selected_system_prompt = system_prompt or build_tracer_system_prompt()
    resolved_tools = _build_tracer_tools(
        trace_storage_service=trace_storage_service,
        sandbox_service=sandbox_service,
    )
    logger.info(
        "Building deep-agent tracer",
        extra={
            "custom_model_provided": model is not None,
            "state_schema": "TracerState",
            "state_field_count": len(_TRACER_STATE_FIELDS),
            "state_fields": _TRACER_STATE_FIELDS,
            "tool_count": len(resolved_tools),
        },
    )
    return create_deep_agent(
        model=model,
        system_prompt=selected_system_prompt,
        tools=resolved_tools,
        middleware=[
            TracerStateSchemaMiddleware(),
            TracerLocalContextMiddleware(sandbox_service=sandbox_service),
            TracerSandboxScopeMiddleware(),
        ],
    )
