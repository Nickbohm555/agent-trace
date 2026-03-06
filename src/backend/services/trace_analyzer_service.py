from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from agents.deep_agent_tracer import build_deep_agent_tracer
from schemas.harness_changes import HarnessChangeFeedback, HarnessChangeSet
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
    harness_feedback: HarnessChangeFeedback | None = None


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
    graph_builder: GraphBuilder = build_deep_agent_tracer

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
            harness_change_set = self._aggregate_harness_change_set(
                base_change_set=harness_change_set,
                feedback=request.harness_feedback,
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
        logger.info(
            "Invoking tracer graph with deep-agent state",
            extra={
                "run_id": run_id,
                "sandbox_path": sandbox_session.sandbox_path,
                "has_max_runtime_seconds": max_runtime_seconds is not None,
                "has_max_steps": max_steps is not None,
            },
        )
        try:
            raw_result = tracer_graph.invoke(graph_state)
        except TypeError as exc:
            if self._is_missing_model_credentials_error(exc):
                logger.warning(
                    "Tracer deep-agent model credentials are missing; continuing with empty graph result",
                    extra={"run_id": run_id, "error": str(exc)},
                )
                return {}
            raise
        coerced_result = self._coerce_graph_result_to_state(raw_result)
        logger.info(
            "Received tracer graph result state",
            extra={
                "run_id": run_id,
                "result_key_count": len(coerced_result.keys()),
                "has_harness_change_set": "harness_change_set" in coerced_result,
                "has_parallel_error_findings": "parallel_error_findings" in coerced_result,
                "parallel_error_count": coerced_result.get("parallel_error_count", 0),
            },
        )
        return coerced_result

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

    @staticmethod
    def _aggregate_harness_change_set(
        *,
        base_change_set: HarnessChangeSet,
        feedback: HarnessChangeFeedback | None,
        run_id: str,
        traces: list[Any],
    ) -> HarnessChangeSet:
        if feedback is None:
            logger.info(
                "Skipping harness change aggregation because no feedback was supplied",
                extra={
                    "run_id": run_id,
                    "base_change_count": len(base_change_set.harness_changes),
                },
            )
            return base_change_set

        trace_ids = TraceAnalyzerService._merge_trace_ids(
            base_trace_ids=base_change_set.trace_ids,
            feedback_trace_ids=feedback.trace_ids,
            traces=traces,
        )
        if feedback.replace_existing_changes:
            merged_changes = list(feedback.harness_changes)
        else:
            merged_changes = list(base_change_set.harness_changes)
            seen_ids = {change.change_id for change in merged_changes}
            for change in feedback.harness_changes:
                if change.change_id in seen_ids:
                    continue
                merged_changes.append(change)
                seen_ids.add(change.change_id)

        merged_summary = feedback.summary.strip() if feedback.summary and feedback.summary.strip() else base_change_set.summary
        aggregated_change_set = HarnessChangeSet(
            run_id=base_change_set.run_id or run_id,
            trace_ids=trace_ids,
            summary=merged_summary,
            harness_changes=merged_changes,
            created_at=base_change_set.created_at,
        )
        logger.info(
            "Aggregated harness changes with external feedback",
            extra={
                "run_id": run_id,
                "base_change_count": len(base_change_set.harness_changes),
                "feedback_change_count": len(feedback.harness_changes),
                "replace_existing_changes": feedback.replace_existing_changes,
                "aggregated_change_count": len(aggregated_change_set.harness_changes),
                "aggregated_trace_id_count": len(aggregated_change_set.trace_ids),
            },
        )
        return aggregated_change_set

    @staticmethod
    def _merge_trace_ids(
        *,
        base_trace_ids: list[str],
        feedback_trace_ids: list[str],
        traces: list[Any],
    ) -> list[str]:
        merged_trace_ids: list[str] = []
        seen_trace_ids: set[str] = set()
        for candidate in [*base_trace_ids, *feedback_trace_ids, *[trace.trace_id for trace in traces]]:
            if candidate in seen_trace_ids:
                continue
            merged_trace_ids.append(candidate)
            seen_trace_ids.add(candidate)
        return merged_trace_ids

    @staticmethod
    def _coerce_graph_result_to_state(raw_result: Any) -> dict[str, Any]:
        if isinstance(raw_result, dict):
            return raw_result

        if hasattr(raw_result, "model_dump"):
            dumped_result = raw_result.model_dump(mode="json")
            if isinstance(dumped_result, dict):
                return dumped_result

        if isinstance(getattr(raw_result, "state", None), dict):
            return dict(raw_result.state)

        logger.warning(
            "Tracer graph returned non-mapping result; coercing to empty state",
            extra={"result_type": type(raw_result).__name__},
        )
        return {}

    @staticmethod
    def _is_missing_model_credentials_error(exc: TypeError) -> bool:
        message = str(exc).lower()
        return (
            "could not resolve authentication method" in message
            or "expected either api_key or auth_token" in message
        )
