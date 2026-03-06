from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, get_type_hints

from deepagents import create_deep_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, hook_config
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.prebuilt.tool_node import ToolCallRequest

from agents.tracer_config import (
    ReasoningLevel,
    ReasoningPhase,
    TracerReasoningConfig,
    resolve_reasoning_level,
    resolve_reasoning_phase,
)
from agents.tracer_context import build_local_context_message, contains_local_context_message
from agents.error_analysis_agent import collect_error_tasks, run_error_analysis_agent_tasks_in_parallel
from agents.harness_change_synthesis import synthesize_harness_changes_from_findings
from agents.tracer_middleware import (
    apply_loop_detection_injection,
    apply_time_budget_injection,
    build_pre_completion_checklist_message,
    should_inject_pre_completion_checklist,
)
from agents.tracer_prompts import build_tracer_system_prompt
from agents.tracer_state import TracerState
from schemas.harness_changes import HarnessChangeSet
from schemas.trace import TraceStorageQuery
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


class TracerParallelErrorAnalysisMiddleware(AgentMiddleware[TracerState, Any, Any]):
    """Run parallel trace error analysis once and inject findings into tracer state."""

    def __init__(self, *, trace_storage_service: TraceStorageService | None) -> None:
        self._trace_storage_service = trace_storage_service

    def before_agent(self, state: TracerState, runtime: Any) -> dict[str, Any] | None:
        del runtime
        if self._trace_storage_service is None:
            return None
        if state.get("parallel_analysis_completed"):
            return None

        run_id = state.get("run_id")
        if not run_id:
            logger.info("Skipping parallel error analysis because run_id is missing")
            return None

        traces = self._trace_storage_service.load_traces(TraceStorageQuery(run_id=run_id, limit=200))
        error_tasks = collect_error_tasks(traces)
        findings = run_error_analysis_agent_tasks_in_parallel(error_tasks)
        payloads = [finding.to_payload() for finding in findings]

        logger.info(
            "Injected parallel error-analysis findings into deep-agent state via invokable agent runner",
            extra={
                "run_id": run_id,
                "error_count": len(error_tasks),
                "finding_count": len(findings),
            },
        )
        return {
            "parallel_error_count": len(error_tasks),
            "parallel_error_findings": payloads,
            "parallel_analysis_completed": True,
        }


class TracerReasoningBudgetMiddleware(AgentMiddleware[TracerState, Any, Any]):
    """Resolve tracer reasoning phase/level and bind model reasoning effort per call."""

    def __init__(self, *, reasoning_config: TracerReasoningConfig | None = None) -> None:
        self._reasoning_config = reasoning_config or TracerReasoningConfig()

    def before_model(self, state: TracerState, runtime: Any) -> dict[str, Any] | None:
        del runtime
        phase, level = self._resolve_reasoning_budget(state)
        return {
            "reasoning_phase": phase,
            "reasoning_level": level,
        }

    def wrap_model_call(self, request: ModelRequest[Any], handler: Any) -> Any:
        state = request.state if isinstance(request.state, dict) else {}
        phase, level = self._resolve_reasoning_budget(state)
        if not self._supports_reasoning_settings(request):
            logger.info(
                "Skipping tracer reasoning model settings for unsupported model provider",
                extra={
                    "run_id": state.get("run_id"),
                    "reasoning_phase": phase,
                    "reasoning_level": level,
                    "model_type": type(getattr(request, "model", None)).__name__,
                },
            )
            return handler(request)

        reasoning_settings = {"effort": level}
        existing_model_settings = request.model_settings if isinstance(request.model_settings, dict) else {}

        logger.info(
            "Applying tracer reasoning budget to deep-agent model call",
            extra={
                "run_id": state.get("run_id"),
                "reasoning_phase": phase,
                "reasoning_level": level,
            },
        )
        return handler(
            request.override(
                model_settings={
                    **existing_model_settings,
                    "reasoning": reasoning_settings,
                }
            )
        )

    @staticmethod
    def _supports_reasoning_settings(request: ModelRequest[Any]) -> bool:
        model = getattr(request, "model", None)
        if model is None:
            return True

        model_module = getattr(type(model), "__module__", "").lower()
        model_name = getattr(type(model), "__name__", "").lower()
        if "anthropic" in model_module or "anthropic" in model_name:
            return False

        return True

    def _resolve_reasoning_budget(self, state: Mapping[str, Any]) -> tuple[ReasoningPhase, ReasoningLevel]:
        phase = resolve_reasoning_phase(state.get("reasoning_phase"))
        phase_levels = self._resolve_phase_levels_with_overrides(state)
        fallback_level = phase_levels.get(phase, self._reasoning_config.default_level)
        level = resolve_reasoning_level(state.get("reasoning_level"), fallback=fallback_level)
        return phase, level

    def _resolve_phase_levels_with_overrides(
        self,
        state: Mapping[str, Any],
    ) -> dict[ReasoningPhase, ReasoningLevel]:
        resolved_levels = dict(self._reasoning_config.phase_levels)
        raw_phase_levels = state.get("reasoning_phase_levels")
        if not isinstance(raw_phase_levels, Mapping):
            return resolved_levels

        for phase in ("planning", "implementation", "verification"):
            raw_level = raw_phase_levels.get(phase)
            if raw_level is None:
                continue
            resolved_levels[phase] = resolve_reasoning_level(
                raw_level,
                fallback=self._reasoning_config.default_level,
            )
        return resolved_levels


class TracerHarnessSynthesisMiddleware(AgentMiddleware[TracerState, Any, Any]):
    """Synthesize structured harness changes from parallel error findings."""

    def after_model(self, state: TracerState, runtime: Any) -> dict[str, Any] | None:
        del runtime
        model_change_set = self._extract_model_synthesized_change_set(state)
        if model_change_set is not None:
            logger.info(
                "Captured model-authored harness changes from synthesis tool call",
                extra={
                    "run_id": state.get("run_id"),
                    "change_count": len(model_change_set.get("harness_changes", [])),
                    "trace_id_count": len(model_change_set.get("trace_ids", [])),
                },
            )
            return {
                "harness_change_set": model_change_set,
                "harness_changes": model_change_set.get("harness_changes", []),
            }

        existing_change_set = state.get("harness_change_set")
        if isinstance(existing_change_set, Mapping) and existing_change_set:
            return None
        if state.get("harness_changes"):
            return None

        synthesized_change_set = synthesize_harness_changes_from_findings(state)
        if synthesized_change_set is None:
            return None

        dumped_change_set = synthesized_change_set.model_dump(mode="json")
        logger.info(
            "Injected synthesized harness changes into deep-agent state",
            extra={
                "run_id": state.get("run_id"),
                "change_count": len(dumped_change_set.get("harness_changes", [])),
                "trace_id_count": len(dumped_change_set.get("trace_ids", [])),
            },
        )
        return {
            "harness_change_set": dumped_change_set,
            "harness_changes": dumped_change_set.get("harness_changes", []),
        }

    @staticmethod
    def _extract_model_synthesized_change_set(state: Mapping[str, Any]) -> dict[str, Any] | None:
        messages = list(state.get("messages", []))
        if not messages or not isinstance(messages[-1], AIMessage):
            return None

        run_id = state.get("run_id")
        for tool_call in reversed(messages[-1].tool_calls or []):
            if tool_call.get("name") != "propose_harness_changes":
                continue
            if not isinstance(tool_call.get("args"), dict):
                continue
            payload = dict(tool_call["args"])
            if not payload.get("run_id") and isinstance(run_id, str):
                payload["run_id"] = run_id
            try:
                parsed = HarnessChangeSet.model_validate(payload)
            except Exception:
                logger.warning(
                    "Ignoring invalid model-authored harness change set payload",
                    extra={"run_id": run_id},
                    exc_info=True,
                )
                return None
            return parsed.model_dump(mode="json")
        return None


class TracerTimeBudgetMiddleware(AgentMiddleware[TracerState, Any, Any]):
    """Apply tracer time/step budget updates and inject warning context when needed."""

    def before_model(self, state: TracerState, runtime: Any) -> dict[str, Any] | None:
        del runtime
        updated_state, budget_message = apply_time_budget_injection(state)
        updates: dict[str, Any] = {
            "run_started_at_epoch_seconds": updated_state.get("run_started_at_epoch_seconds"),
            "agent_step_count": updated_state.get("agent_step_count"),
        }
        if "time_budget_last_notice_step" in updated_state:
            updates["time_budget_last_notice_step"] = updated_state.get("time_budget_last_notice_step")
        if budget_message is not None:
            updates["messages"] = [budget_message]
        return updates


class TracerPreCompletionVerificationMiddleware(AgentMiddleware[TracerState, Any, Any]):
    """Force one verification turn before allowing deep-agent completion."""

    @hook_config(can_jump_to=["model"])
    def after_model(self, state: TracerState, runtime: Any) -> dict[str, Any] | None:
        del runtime
        if not should_inject_pre_completion_checklist(state):
            return None

        checklist_message = build_pre_completion_checklist_message(state)
        logger.info(
            "Injecting pre-completion verification checklist in deep-agent middleware",
            extra={"run_id": state.get("run_id")},
        )
        return {
            "messages": [SystemMessage(content=checklist_message)],
            "pre_completion_verified": True,
            "jump_to": "model",
        }


class TracerLoopDetectionMiddleware(AgentMiddleware[TracerState, Any, Any]):
    """Track repeated edit_file tool calls and inject anti-loop guidance."""

    def after_model(self, state: TracerState, runtime: Any) -> dict[str, Any] | None:
        del runtime
        messages = list(state.get("messages", []))
        if not messages or not isinstance(messages[-1], AIMessage):
            return None

        updated_state, loop_message = apply_loop_detection_injection(
            state,
            response=messages[-1],
        )
        updates: dict[str, Any] = {
            "edit_file_counts": updated_state.get("edit_file_counts", {}),
            "loop_detection_nudged_files": updated_state.get("loop_detection_nudged_files", []),
        }
        if loop_message is not None:
            updates["messages"] = [loop_message]
            logger.info(
                "Injected deep-agent loop-detection notice",
                extra={
                    "run_id": state.get("run_id"),
                    "nudged_files": updates["loop_detection_nudged_files"],
                },
            )
        return updates


def build_propose_harness_changes_tool() -> BaseTool:
    """Create a tool that validates and returns model-authored HarnessChangeSet payloads."""

    def _propose_harness_changes(
        run_id: str | None = None,
        trace_ids: list[str] | None = None,
        summary: str | None = None,
        harness_changes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        change_set = HarnessChangeSet(
            run_id=run_id,
            trace_ids=trace_ids or [],
            summary=summary,
            harness_changes=harness_changes or [],
        )
        dumped = change_set.model_dump(mode="json")
        return {
            "accepted": True,
            "harness_change_set": dumped,
            "change_count": len(dumped.get("harness_changes", [])),
        }

    return StructuredTool.from_function(
        name="propose_harness_changes",
        description=(
            "Propose a structured harness change set synthesized from parallel error findings. "
            "Use this tool to submit run_id, trace_ids, summary, and harness_changes."
        ),
        func=_propose_harness_changes,
    )


def _build_tracer_tools(
    *,
    trace_storage_service: TraceStorageService | None,
    sandbox_service: SandboxService | None,
) -> list[BaseTool]:
    tools: list[BaseTool] = [build_propose_harness_changes_tool()]
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
    reasoning_config: TracerReasoningConfig | None = None,
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
            TracerParallelErrorAnalysisMiddleware(trace_storage_service=trace_storage_service),
            TracerHarnessSynthesisMiddleware(),
            TracerLocalContextMiddleware(sandbox_service=sandbox_service),
            TracerSandboxScopeMiddleware(),
            TracerTimeBudgetMiddleware(),
            TracerReasoningBudgetMiddleware(reasoning_config=reasoning_config),
            TracerLoopDetectionMiddleware(),
            TracerPreCompletionVerificationMiddleware(),
        ],
    )
