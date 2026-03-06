from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from schemas.trace import StoredTrace

logger = logging.getLogger(__name__)

_DEFAULT_FIX_CATEGORY = "unknown"
_DEFAULT_ROOT_CAUSE = "Insufficient signal to determine root cause."


@dataclass(frozen=True)
class TraceErrorTask:
    trace_id: str
    scope: str
    span_id: str | None
    message: str | None
    error_type: str | None


@dataclass(frozen=True)
class ErrorAnalysisFinding:
    trace_id: str
    scope: str
    span_id: str | None
    root_cause: str
    suggested_fix_category: str
    confidence: float
    error_message: str | None = None
    error_type: str | None = None

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


AnalyzerFn = Callable[[TraceErrorTask], ErrorAnalysisFinding | Awaitable[ErrorAnalysisFinding]]
ErrorAnalysisAgentAnalyzerFn = Callable[
    [TraceErrorTask],
    (
        ErrorAnalysisFinding
        | Sequence[ErrorAnalysisFinding]
        | Awaitable[ErrorAnalysisFinding | Sequence[ErrorAnalysisFinding]]
    ),
]
class ErrorAnalysisAgentState(TypedDict, total=False):
    task: TraceErrorTask
    findings: list[ErrorAnalysisFinding]


def collect_error_tasks(traces: list[StoredTrace]) -> list[TraceErrorTask]:
    tasks: list[TraceErrorTask] = []
    seen: set[tuple[str, str, str | None, str | None, str | None]] = set()

    for trace in traces:
        for item in trace.errors:
            scope = str(item.get("scope") or "trace")
            span_id_value = item.get("span_id")
            span_id = str(span_id_value) if span_id_value is not None else None
            message_value = item.get("message")
            message = str(message_value) if message_value is not None else None
            error_type_value = item.get("error_type")
            error_type = str(error_type_value) if error_type_value is not None else None
            key = (trace.trace_id, scope, span_id, message, error_type)
            if key in seen:
                continue
            seen.add(key)
            tasks.append(
                TraceErrorTask(
                    trace_id=trace.trace_id,
                    scope=scope,
                    span_id=span_id,
                    message=message,
                    error_type=error_type,
                )
            )

    logger.info("Collected trace errors for parallel analysis", extra={"error_count": len(tasks)})
    return tasks


def _default_error_analyzer(task: TraceErrorTask) -> ErrorAnalysisFinding:
    text = f"{task.error_type or ''} {task.message or ''}".lower()

    root_cause = _DEFAULT_ROOT_CAUSE
    fix_category = _DEFAULT_FIX_CATEGORY
    confidence = 0.4

    if "timeout" in text or "deadline" in text:
        root_cause = "A timeout occurred while waiting for tool or model completion."
        fix_category = "timeout_or_retry_policy"
        confidence = 0.85
    elif "validation" in text or "schema" in text:
        root_cause = "Input/output schema mismatch caused validation failure."
        fix_category = "schema_contract"
        confidence = 0.8
    elif "permission" in text or "denied" in text:
        root_cause = "Access control or sandbox permission restriction blocked execution."
        fix_category = "environment_permissions"
        confidence = 0.8
    elif "not found" in text or "no such file" in text:
        root_cause = "Referenced path or resource does not exist in the sandbox context."
        fix_category = "path_resolution"
        confidence = 0.78
    elif "json" in text or "parse" in text:
        root_cause = "Malformed or unexpected structured output could not be parsed."
        fix_category = "structured_output_format"
        confidence = 0.75

    return ErrorAnalysisFinding(
        trace_id=task.trace_id,
        scope=task.scope,
        span_id=task.span_id,
        root_cause=root_cause,
        suggested_fix_category=fix_category,
        confidence=confidence,
        error_message=task.message,
        error_type=task.error_type,
    )


def _default_error_analysis_agent_analyzer(task: TraceErrorTask) -> list[ErrorAnalysisFinding]:
    return [_default_error_analyzer(task)]


def _normalize_agent_findings(
    findings: ErrorAnalysisFinding | Sequence[ErrorAnalysisFinding],
) -> list[ErrorAnalysisFinding]:
    if isinstance(findings, ErrorAnalysisFinding):
        return [findings]
    return list(findings)


def build_error_analysis_agent(*, analyzer: ErrorAnalysisAgentAnalyzerFn | None = None) -> Any:
    selected_analyzer = analyzer or _default_error_analysis_agent_analyzer

    async def _analyze_task(state: ErrorAnalysisAgentState) -> ErrorAnalysisAgentState:
        task = state["task"]
        result = selected_analyzer(task)
        if asyncio.iscoroutine(result):
            result = await result
        findings = _normalize_agent_findings(result)
        logger.info(
            "Completed invokable error-analysis agent task",
            extra={
                "trace_id": task.trace_id,
                "scope": task.scope,
                "span_id": task.span_id,
                "finding_count": len(findings),
            },
        )
        return {"findings": findings}

    graph = StateGraph(ErrorAnalysisAgentState)
    graph.add_node("analyze_task", _analyze_task)
    graph.add_edge(START, "analyze_task")
    graph.add_edge("analyze_task", END)
    return graph.compile()


async def run_error_analysis_agent_async(
    task: TraceErrorTask,
    *,
    analyzer: ErrorAnalysisAgentAnalyzerFn | None = None,
) -> list[ErrorAnalysisFinding]:
    graph = build_error_analysis_agent(analyzer=analyzer)
    result = await graph.ainvoke({"task": task})
    findings = result.get("findings", []) if isinstance(result, dict) else []
    logger.info(
        "Ran invokable error-analysis agent",
        extra={
            "trace_id": task.trace_id,
            "scope": task.scope,
            "span_id": task.span_id,
            "finding_count": len(findings),
        },
    )
    return findings


def run_error_analysis_agent(
    task: TraceErrorTask,
    *,
    analyzer: ErrorAnalysisAgentAnalyzerFn | None = None,
) -> list[ErrorAnalysisFinding]:
    return asyncio.run(run_error_analysis_agent_async(task, analyzer=analyzer))


async def _run_single_analysis(
    task: TraceErrorTask,
    *,
    analyzer: AnalyzerFn,
    semaphore: asyncio.Semaphore,
) -> ErrorAnalysisFinding:
    async with semaphore:
        result = analyzer(task)
        if asyncio.iscoroutine(result):
            return await result
        return result


async def _run_single_agent_analysis(
    task: TraceErrorTask,
    *,
    agent_analyzer: ErrorAnalysisAgentAnalyzerFn | None,
    semaphore: asyncio.Semaphore,
    fallback_to_rule_based: bool,
) -> list[ErrorAnalysisFinding]:
    async with semaphore:
        try:
            return await run_error_analysis_agent_async(task, analyzer=agent_analyzer)
        except Exception:
            if not fallback_to_rule_based:
                raise
            logger.exception(
                "Error-analysis agent task failed; falling back to rule-based analyzer",
                extra={
                    "trace_id": task.trace_id,
                    "scope": task.scope,
                    "span_id": task.span_id,
                },
            )
            return [_default_error_analyzer(task)]


async def run_error_analysis_agent_tasks_in_parallel_async(
    tasks: list[TraceErrorTask],
    *,
    agent_analyzer: ErrorAnalysisAgentAnalyzerFn | None = None,
    max_concurrency: int = 8,
    fallback_to_rule_based: bool = True,
) -> list[ErrorAnalysisFinding]:
    if not tasks:
        return []

    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    jobs = [
        _run_single_agent_analysis(
            task,
            agent_analyzer=agent_analyzer,
            semaphore=semaphore,
            fallback_to_rule_based=fallback_to_rule_based,
        )
        for task in tasks
    ]
    nested_findings = await asyncio.gather(*jobs)
    findings = [finding for task_findings in nested_findings for finding in task_findings]
    logger.info(
        "Completed parallel invokable error-analysis agent execution",
        extra={
            "task_count": len(tasks),
            "finding_count": len(findings),
            "max_concurrency": max(1, max_concurrency),
            "fallback_to_rule_based": fallback_to_rule_based,
        },
    )
    return findings


def run_error_analysis_agent_tasks_in_parallel(
    tasks: list[TraceErrorTask],
    *,
    agent_analyzer: ErrorAnalysisAgentAnalyzerFn | None = None,
    max_concurrency: int = 8,
    fallback_to_rule_based: bool = True,
) -> list[ErrorAnalysisFinding]:
    return asyncio.run(
        run_error_analysis_agent_tasks_in_parallel_async(
            tasks,
            agent_analyzer=agent_analyzer,
            max_concurrency=max_concurrency,
            fallback_to_rule_based=fallback_to_rule_based,
        )
    )


async def analyze_errors_in_parallel_async(
    tasks: list[TraceErrorTask],
    *,
    analyzer: AnalyzerFn | None = None,
    max_concurrency: int = 8,
) -> list[ErrorAnalysisFinding]:
    if not tasks:
        return []

    selected_analyzer = analyzer or _default_error_analyzer
    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    jobs = [
        _run_single_analysis(
            task,
            analyzer=selected_analyzer,
            semaphore=semaphore,
        )
        for task in tasks
    ]
    findings = await asyncio.gather(*jobs)
    logger.info(
        "Completed parallel error analysis",
        extra={
            "error_count": len(tasks),
            "finding_count": len(findings),
            "max_concurrency": max(1, max_concurrency),
        },
    )
    return findings


def analyze_errors_in_parallel(
    tasks: list[TraceErrorTask],
    *,
    analyzer: AnalyzerFn | None = None,
    max_concurrency: int = 8,
) -> list[ErrorAnalysisFinding]:
    return asyncio.run(
        analyze_errors_in_parallel_async(
            tasks,
            analyzer=analyzer,
            max_concurrency=max_concurrency,
        )
    )
