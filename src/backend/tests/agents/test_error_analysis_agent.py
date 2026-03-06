from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from agents.error_analysis_agent import (
    ErrorAnalysisFinding,
    TraceErrorTask,
    analyze_errors_in_parallel,
    collect_error_tasks,
)
from schemas.trace import NormalizedTraceSpan, StoredTrace


def test_collect_error_tasks_deduplicates_trace_errors() -> None:
    traces = [
        StoredTrace(
            trace_id="trace-1",
            run_id="run-1",
            errors=[
                {"scope": "trace", "message": "timeout", "error_type": "TimeoutError"},
                {"scope": "trace", "message": "timeout", "error_type": "TimeoutError"},
                {
                    "scope": "span",
                    "span_id": "span-1",
                    "message": "bad schema",
                    "error_type": "ValidationError",
                },
            ],
            spans=[
                NormalizedTraceSpan(
                    span_id="span-1",
                    start_time=datetime(2026, 3, 6, tzinfo=timezone.utc),
                )
            ],
        )
    ]

    tasks = collect_error_tasks(traces)

    assert len(tasks) == 2
    assert tasks[0].trace_id == "trace-1"
    assert tasks[1].span_id == "span-1"


def test_analyze_errors_in_parallel_runs_multiple_workers_concurrently() -> None:
    tasks = [
        TraceErrorTask(
            trace_id=f"trace-{idx}",
            scope="trace",
            span_id=None,
            message="timeout",
            error_type="TimeoutError",
        )
        for idx in range(6)
    ]

    active_workers = 0
    max_active_workers = 0

    async def analyzer(task: TraceErrorTask) -> ErrorAnalysisFinding:
        nonlocal active_workers, max_active_workers
        active_workers += 1
        max_active_workers = max(max_active_workers, active_workers)
        await asyncio.sleep(0.01)
        active_workers -= 1
        return ErrorAnalysisFinding(
            trace_id=task.trace_id,
            scope=task.scope,
            span_id=task.span_id,
            root_cause="timeout detected",
            suggested_fix_category="timeout_or_retry_policy",
            confidence=0.9,
            error_message=task.message,
            error_type=task.error_type,
        )

    findings = analyze_errors_in_parallel(tasks, analyzer=analyzer, max_concurrency=4)

    assert len(findings) == 6
    assert max_active_workers > 1
    assert findings[0].suggested_fix_category == "timeout_or_retry_policy"
