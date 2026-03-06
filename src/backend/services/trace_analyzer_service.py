from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from agents.langgraph_agent import build_tracer_graph
from schemas.harness_changes import HarnessChangeSet
from schemas.improvement_metrics import ImprovementMetrics
from schemas.sandbox import SandboxCreateRequest, SandboxSession
from schemas.trace import NormalizedTrace, TraceQueryFilters, TraceStorageQuery
from services.improvement_metrics_service import (
    EvaluationCommandConfig,
    ImprovementMetricsRequest,
    ImprovementMetricsService,
)
from services.langfuse_trace_service import LangfuseTraceService
from services.sandbox_service import SandboxService
from services.trace_storage_service import TraceStorageService

logger = logging.getLogger(__name__)

GraphBuilder = Callable[..., Any]


@dataclass(frozen=True)
class TraceAnalyzerRequest:
    run_id: str
    target_repo_url: str | None = None
    trace_ids: list[str] | None = None
    run_name: str | None = None
    from_timestamp: datetime | None = None
    to_timestamp: datetime | None = None
    limit: int = 50
    environment: str | None = None
    evaluation_command: list[str] | None = None
    evaluation_cwd: str | None = None
    evaluation_timeout_seconds: int = 900
    max_runtime_seconds: int | None = None
    max_steps: int | None = None


@dataclass(frozen=True)
class TraceAnalyzerResult:
    run_id: str
    target_repo_url: str
    trace_ids: list[str]
    fetched_trace_count: int
    persisted_trace_count: int
    loaded_trace_count: int
    harness_change_set: HarnessChangeSet
    improvement_metrics: ImprovementMetrics | None = None


@dataclass
class TraceAnalyzerService:
    """Orchestrate Trace Analyzer flow: fetch -> store/load -> analyze -> synthesize."""

    langfuse_trace_service: LangfuseTraceService
    trace_storage_service: TraceStorageService
    sandbox_service: SandboxService
    improvement_metrics_service: ImprovementMetricsService | None = None
    graph_builder: GraphBuilder = build_tracer_graph

    def analyze(self, request: TraceAnalyzerRequest) -> TraceAnalyzerResult:
        logger.info(
            "Starting trace analyzer orchestration",
            extra={
                "run_id": request.run_id,
                "target_repo_url": request.target_repo_url,
                "trace_id_count": len(request.trace_ids or []),
                "run_name": request.run_name,
            },
        )

        fetched_traces = self.langfuse_trace_service.fetch_traces(
            TraceQueryFilters(
                trace_ids=request.trace_ids,
                run_name=request.run_name,
                from_timestamp=request.from_timestamp,
                to_timestamp=request.to_timestamp,
                limit=request.limit,
                environment=request.environment,
            )
        )

        traces_for_storage = self._coerce_traces_to_run_id(
            fetched_traces,
            run_id=request.run_id,
        )
        persisted_trace_count = self.trace_storage_service.save_traces(traces_for_storage)
        loaded_traces = self.trace_storage_service.load_traces(
            TraceStorageQuery(run_id=request.run_id, limit=max(request.limit, 1))
        )

        # Fallback for callers that provide explicit trace IDs but no run match in storage.
        if not loaded_traces and request.trace_ids:
            loaded_traces = self.trace_storage_service.load_traces(
                TraceStorageQuery(trace_ids=request.trace_ids, limit=max(request.limit, 1))
            )

        sandbox_session: SandboxSession | None = None
        improvement_metrics: ImprovementMetrics | None = None
        try:
            sandbox_session = self.sandbox_service.create_sandbox(
                SandboxCreateRequest(target_repo_url=request.target_repo_url)
            )
            graph_result: dict[str, Any] = {}
            if request.evaluation_command:
                metrics_service = self.improvement_metrics_service or ImprovementMetricsService(
                    sandbox_service=self.sandbox_service
                )
                graph_result_holder: dict[str, dict[str, Any]] = {}

                def run_tracer_between_evaluations() -> None:
                    graph_result_holder["value"] = self._invoke_tracer_graph(
                        run_id=request.run_id,
                        sandbox_session=sandbox_session,
                        max_runtime_seconds=request.max_runtime_seconds,
                        max_steps=request.max_steps,
                    )

                improvement_metrics = metrics_service.measure_improvement(
                    ImprovementMetricsRequest(
                        sandbox_session=sandbox_session,
                        baseline=EvaluationCommandConfig(
                            command=request.evaluation_command,
                            cwd=request.evaluation_cwd,
                            timeout_seconds=request.evaluation_timeout_seconds,
                        ),
                    ),
                    between_runs=run_tracer_between_evaluations,
                )
                graph_result = graph_result_holder.get("value", {})
            else:
                graph_result = self._invoke_tracer_graph(
                    run_id=request.run_id,
                    sandbox_session=sandbox_session,
                    max_runtime_seconds=request.max_runtime_seconds,
                    max_steps=request.max_steps,
                )
            harness_change_set = self._build_change_set_from_graph_result(
                graph_result=graph_result,
                run_id=request.run_id,
                traces=loaded_traces,
            )
        finally:
            if sandbox_session is not None:
                self.sandbox_service.teardown_sandbox(sandbox_session)

        logger.info(
            "Completed trace analyzer orchestration",
            extra={
                "run_id": request.run_id,
                "fetched_trace_count": len(fetched_traces),
                "persisted_trace_count": persisted_trace_count,
                "loaded_trace_count": len(loaded_traces),
                "harness_change_count": len(harness_change_set.harness_changes),
                "improvement_metrics_available": improvement_metrics is not None,
            },
        )

        return TraceAnalyzerResult(
            run_id=request.run_id,
            target_repo_url=sandbox_session.target_repo_url if sandbox_session else "unknown",
            trace_ids=[trace.trace_id for trace in loaded_traces],
            fetched_trace_count=len(fetched_traces),
            persisted_trace_count=persisted_trace_count,
            loaded_trace_count=len(loaded_traces),
            harness_change_set=harness_change_set,
            improvement_metrics=improvement_metrics,
        )

    def _invoke_tracer_graph(
        self,
        *,
        run_id: str,
        sandbox_session: SandboxSession,
        max_runtime_seconds: int | None = None,
        max_steps: int | None = None,
    ) -> dict[str, Any]:
        tracer_graph = self.graph_builder(
            trace_storage_service=self.trace_storage_service,
            sandbox_service=self.sandbox_service,
        )
        graph_state: dict[str, Any] = {
            "messages": [],
            "run_id": run_id,
            "sandbox_path": sandbox_session.sandbox_path,
            "pre_completion_verified": True,
        }
        if max_runtime_seconds is not None:
            graph_state["max_runtime_seconds"] = max_runtime_seconds
        if max_steps is not None:
            graph_state["max_steps"] = max_steps
        return tracer_graph.invoke(
            graph_state
        )

    @staticmethod
    def _coerce_traces_to_run_id(traces: list[NormalizedTrace], *, run_id: str) -> list[NormalizedTrace]:
        coerced: list[NormalizedTrace] = []
        for trace in traces:
            if trace.run_id:
                coerced.append(trace)
            else:
                coerced.append(trace.model_copy(update={"run_id": run_id}))
        return coerced

    @staticmethod
    def _build_change_set_from_graph_result(
        *,
        graph_result: dict[str, Any],
        run_id: str,
        traces: list[Any],
    ) -> HarnessChangeSet:
        dumped_change_set = graph_result.get("harness_change_set")
        if isinstance(dumped_change_set, dict):
            return HarnessChangeSet.model_validate(dumped_change_set)

        return HarnessChangeSet(
            run_id=run_id,
            trace_ids=[trace.trace_id for trace in traces],
            summary="No harness changes were synthesized by the tracer graph.",
            harness_changes=[],
        )
