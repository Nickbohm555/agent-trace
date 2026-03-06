from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.messages import AIMessage, AnyMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from agents.tracer_config import (
    ReasoningLevel,
    ReasoningPhase,
    TracerReasoningConfig,
    resolve_reasoning_level,
    resolve_reasoning_phase,
)
from agents.tracer_context import build_local_context_message, contains_local_context_message
from agents.error_analysis_agent import (
    analyze_errors_in_parallel,
    collect_error_tasks,
)
from agents.tracer_middleware import (
    apply_loop_detection_injection,
    apply_time_budget_injection,
    pre_completion_check_node,
    should_inject_pre_completion_checklist,
)
from schemas.harness_changes import (
    HarnessChange,
    HarnessChangeSet,
    SuggestedConfigChange,
    SuggestedPromptEdit,
    SuggestedToolChange,
)
from schemas.trace import TraceStorageQuery
from agents.tracer_prompts import build_tracer_system_prompt
from agents.tracer_state import TracerState
from services.sandbox_service import SandboxService
from services.trace_storage_service import TraceStorageService
from tools.codebase_tools import build_edit_file_tool, build_list_directory_tool, build_read_file_tool
from tools.sandbox_tools import build_run_command_tool
from tools.trace_tools import build_read_trace_tool

logger = logging.getLogger(__name__)

ModelInvoke = Callable[[TracerState, ReasoningPhase, ReasoningLevel], AIMessage]


def should_continue(state: TracerState) -> Literal["continue", "verify", "end"]:
    """Route to tools, verification middleware, or end based on latest model output."""
    messages: list[AnyMessage] = state.get("messages", [])
    if not messages:
        logger.info("Tracer graph ending because no messages are present")
        return "end"

    last_message = messages[-1]
    has_tool_calls = bool(getattr(last_message, "tool_calls", None))
    if has_tool_calls:
        route = "continue"
    elif should_inject_pre_completion_checklist(state):
        route = "verify"
    else:
        route = "end"
    logger.info("Tracer graph conditional route selected", extra={"route": route})
    return route


def default_agent_node(_: TracerState) -> dict[str, list[AIMessage]]:
    """Minimal agent node for section 4 graph backbone; tools are added later."""
    logger.info("Executing default tracer agent node")
    return {"messages": [AIMessage(content="Tracer graph skeleton response.")]}


def default_model_invoke(_: TracerState, __: ReasoningPhase, ___: ReasoningLevel) -> AIMessage:
    """Default model adapter placeholder until tool-bound agent execution is added."""
    return AIMessage(content="Tracer graph skeleton response.")


def _inject_system_prompt(state: TracerState, system_prompt: str) -> TracerState:
    messages: list[AnyMessage] = list(state.get("messages", []))
    if messages and isinstance(messages[0], SystemMessage) and system_prompt in str(messages[0].content):
        return state

    prompted_state: TracerState = dict(state)
    prompted_state["messages"] = [SystemMessage(content=system_prompt), *messages]
    return prompted_state


def _inject_local_context(
    state: TracerState,
    *,
    sandbox_service: SandboxService | None,
) -> TracerState:
    if sandbox_service is None:
        return state

    sandbox_path = state.get("sandbox_path")
    if not sandbox_path:
        return state

    messages: list[AnyMessage] = list(state.get("messages", []))
    if contains_local_context_message(messages):
        return state

    context_message = state.get("local_context")
    if not context_message:
        context_message = build_local_context_message(
            sandbox_service=sandbox_service,
            sandbox_path=sandbox_path,
        )

    contextual_state: TracerState = dict(state)
    contextual_state["local_context"] = context_message
    contextual_state["messages"] = [SystemMessage(content=context_message), *messages]
    logger.info(
        "Injected tracer local context",
        extra={"sandbox_path": sandbox_path, "run_id": state.get("run_id")},
    )
    return contextual_state


def _inject_parallel_error_analysis(
    state: TracerState,
    *,
    trace_storage_service: TraceStorageService | None,
) -> TracerState:
    if trace_storage_service is None:
        return state
    if state.get("parallel_analysis_completed"):
        return state

    run_id = state.get("run_id")
    if not run_id:
        logger.info("Skipping parallel error analysis because run_id is missing")
        return state

    traces = trace_storage_service.load_traces(TraceStorageQuery(run_id=run_id, limit=200))
    error_tasks = collect_error_tasks(traces)
    findings = analyze_errors_in_parallel(error_tasks)

    updated_state: TracerState = dict(state)
    updated_state["parallel_error_count"] = len(error_tasks)
    updated_state["parallel_error_findings"] = [finding.to_payload() for finding in findings]
    updated_state["parallel_analysis_completed"] = True
    logger.info(
        "Injected parallel error-analysis findings into tracer state",
        extra={
            "run_id": run_id,
            "error_count": len(error_tasks),
            "finding_count": len(findings),
        },
    )
    return updated_state


def _synthesize_harness_changes(state: TracerState) -> HarnessChangeSet | None:
    findings = state.get("parallel_error_findings", [])
    if not findings:
        return None

    grouped_counts: dict[str, int] = {}
    trace_ids: set[str] = set()
    for finding in findings:
        fix_category = str(finding.get("suggested_fix_category") or "unknown")
        grouped_counts[fix_category] = grouped_counts.get(fix_category, 0) + 1
        trace_id = finding.get("trace_id")
        if isinstance(trace_id, str) and trace_id:
            trace_ids.add(trace_id)

    sorted_categories = sorted(
        grouped_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )
    harness_changes: list[HarnessChange] = []

    for index, (fix_category, count) in enumerate(sorted_categories, start=1):
        if fix_category == "timeout_or_retry_policy":
            harness_change = HarnessChange(
                change_id=f"hc-{index:03d}",
                title="Tune execution timeout and retry strategy",
                category="config",
                confidence=0.82,
                config_change=SuggestedConfigChange(
                    key="sandbox.command_timeout_seconds",
                    action="increase",
                    value=180,
                    scope="sandbox",
                    rationale=(
                        f"{count} failing trace(s) indicate timeout-related failures; "
                        "increase timeout to reduce premature command termination."
                    ),
                ),
            )
        elif fix_category in {"schema_contract", "structured_output_format"}:
            harness_change = HarnessChange(
                change_id=f"hc-{index:03d}",
                title="Tighten structured-output schema instructions",
                category="prompt",
                confidence=0.8,
                prompt_edit=SuggestedPromptEdit(
                    target="verification_prompt",
                    action="append",
                    instruction=(
                        "Before finalizing tool or model output, validate it against the expected "
                        "schema and include explicit field-level checks."
                    ),
                    rationale=(
                        f"{count} failing trace(s) show schema/format mismatches; stronger "
                        "verification prompt guidance reduces parse and contract failures."
                    ),
                    expected_outcome="Fewer invalid structured responses and parsing errors.",
                ),
            )
        elif fix_category == "path_resolution":
            harness_change = HarnessChange(
                change_id=f"hc-{index:03d}",
                title="Improve path discovery and file-resolution tooling",
                category="tool",
                confidence=0.76,
                tool_change=SuggestedToolChange(
                    tool_name="read_file",
                    action="update",
                    change_summary=(
                        "Add pre-read path checks and suggested nearest matching files when a "
                        "path is missing."
                    ),
                    rationale=(
                        f"{count} failing trace(s) indicate missing files or bad paths; "
                        "tool-assisted path resolution lowers repeated lookup failures."
                    ),
                    interface={"inputs": ["sandbox_path", "path"], "returns": "content_or_suggestions"},
                ),
            )
        elif fix_category == "environment_permissions":
            harness_change = HarnessChange(
                change_id=f"hc-{index:03d}",
                title="Clarify sandbox execution permissions",
                category="config",
                confidence=0.75,
                config_change=SuggestedConfigChange(
                    key="sandbox.allowed_commands",
                    action="set",
                    value=["pytest", "npm", "uv", "python", "sh"],
                    scope="sandbox",
                    rationale=(
                        f"{count} failing trace(s) indicate permission denials; a clear allowlist "
                        "helps keep execution safe while unblocking expected workflows."
                    ),
                ),
            )
        else:
            harness_change = HarnessChange(
                change_id=f"hc-{index:03d}",
                title="Strengthen plan-build-verify alignment",
                category="prompt",
                confidence=0.65,
                prompt_edit=SuggestedPromptEdit(
                    target="system_prompt",
                    action="append",
                    instruction=(
                        "When root cause is uncertain, explicitly restate assumptions, run one "
                        "targeted diagnostic command, then revise the plan before additional edits."
                    ),
                    rationale=(
                        f"{count} failing trace(s) lacked a specific fix category; a stricter "
                        "diagnostic loop reduces speculative edits."
                    ),
                    expected_outcome="Lower repeat failures from ambiguous root-cause analysis.",
                ),
            )
        harness_changes.append(harness_change)

    summary = (
        "Synthesized harness changes from parallel error analysis; "
        f"{len(findings)} finding(s) across {len(sorted_categories)} fix category(ies)."
    )
    change_set = HarnessChangeSet(
        run_id=state.get("run_id"),
        trace_ids=sorted(trace_ids),
        summary=summary,
        harness_changes=harness_changes,
    )
    logger.info(
        "Synthesized structured harness changes",
        extra={
            "run_id": state.get("run_id"),
            "finding_count": len(findings),
            "change_count": len(harness_changes),
            "categories": [category for category, _ in sorted_categories],
        },
    )
    return change_set


def build_tracer_graph(
    agent_node: Callable[[TracerState], dict[str, list[AnyMessage]]] | None = None,
    *,
    model_invoke: ModelInvoke | None = None,
    reasoning_config: TracerReasoningConfig | None = None,
    trace_storage_service: TraceStorageService | None = None,
    sandbox_service: SandboxService | None = None,
    tools: list[BaseTool] | None = None,
    system_prompt: str | None = None,
) -> Any:
    """Build the Section 4 LangGraph skeleton for the tracer deep-agent loop."""
    resolved_tools = list(tools or [])
    if trace_storage_service is not None:
        resolved_tools.append(build_read_trace_tool(trace_storage_service))
    if sandbox_service is not None:
        resolved_tools.append(build_list_directory_tool(sandbox_service))
        resolved_tools.append(build_read_file_tool(sandbox_service))
        resolved_tools.append(build_edit_file_tool(sandbox_service))
        resolved_tools.append(build_run_command_tool(sandbox_service))

    if agent_node is None:
        selected_reasoning_config = reasoning_config or TracerReasoningConfig()
        selected_model_invoke = model_invoke or default_model_invoke
        selected_system_prompt = system_prompt or build_tracer_system_prompt()

        def configured_agent_node(state: TracerState) -> dict[str, list[AnyMessage]]:
            phase = resolve_reasoning_phase(state.get("reasoning_phase"))
            level = resolve_reasoning_level(
                state.get("reasoning_level"),
                fallback=selected_reasoning_config.level_for_phase(phase),
            )
            analyzed_state = _inject_parallel_error_analysis(
                state,
                trace_storage_service=trace_storage_service,
            )
            contextual_state = _inject_local_context(analyzed_state, sandbox_service=sandbox_service)
            prompted_state = _inject_system_prompt(contextual_state, selected_system_prompt)
            budgeted_state, time_budget_message = apply_time_budget_injection(prompted_state)
            invoke_state = budgeted_state
            if time_budget_message is not None:
                invoke_state = dict(budgeted_state)
                invoke_state["messages"] = [*list(budgeted_state.get("messages", [])), time_budget_message]
            logger.info(
                "Executing tracer agent with reasoning configuration",
                extra={"phase": phase, "reasoning_level": level, "run_id": state.get("run_id")},
            )
            response = selected_model_invoke(invoke_state, phase, level)
            loop_detection_state, loop_detection_message = apply_loop_detection_injection(
                budgeted_state,
                response=response,
            )
            output_messages: list[AnyMessage] = [response]
            if time_budget_message is not None:
                output_messages = [time_budget_message, *output_messages]
            if loop_detection_message is not None:
                output_messages = [*output_messages[:-1], loop_detection_message, output_messages[-1]]
            updates: dict[str, Any] = {
                "messages": output_messages,
                "agent_step_count": loop_detection_state["agent_step_count"],
                "run_started_at_epoch_seconds": loop_detection_state["run_started_at_epoch_seconds"],
                "edit_file_counts": loop_detection_state.get("edit_file_counts", {}),
                "loop_detection_nudged_files": loop_detection_state.get("loop_detection_nudged_files", []),
            }
            if "time_budget_last_notice_step" in loop_detection_state:
                updates["time_budget_last_notice_step"] = loop_detection_state["time_budget_last_notice_step"]
            if contextual_state.get("local_context") and not state.get("local_context"):
                updates["local_context"] = contextual_state["local_context"]
            if "parallel_error_count" in analyzed_state:
                updates["parallel_error_count"] = analyzed_state["parallel_error_count"]
            if "parallel_error_findings" in analyzed_state:
                updates["parallel_error_findings"] = analyzed_state["parallel_error_findings"]
            if analyzed_state.get("parallel_analysis_completed"):
                updates["parallel_analysis_completed"] = True
            synthesized_harness_changes = _synthesize_harness_changes(analyzed_state)
            if synthesized_harness_changes is not None:
                dumped_change_set = synthesized_harness_changes.model_dump(mode="json")
                updates["harness_change_set"] = dumped_change_set
                updates["harness_changes"] = dumped_change_set["harness_changes"]
            return updates

        resolved_agent_node = configured_agent_node
    else:
        resolved_agent_node = agent_node

    graph = StateGraph(TracerState)
    graph.add_node("agent", resolved_agent_node)
    graph.add_node("pre_completion_check", pre_completion_check_node)
    if resolved_tools:
        graph.add_node("tools", ToolNode(resolved_tools))

    graph.add_edge(START, "agent")
    if resolved_tools:
        graph.add_conditional_edges(
            "agent",
            should_continue,
            {
                "continue": "tools",
                "verify": "pre_completion_check",
                "end": END,
            },
        )
        graph.add_edge("tools", "agent")
    else:
        graph.add_conditional_edges(
            "agent",
            should_continue,
            {
                "continue": "agent",
                "verify": "pre_completion_check",
                "end": END,
            },
        )
    graph.add_edge("pre_completion_check", "agent")
    return graph.compile()
