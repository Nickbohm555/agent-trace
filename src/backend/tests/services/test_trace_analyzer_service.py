from __future__ import annotations

from datetime import datetime, timezone

from schemas.harness_changes import HarnessChangeSet
from schemas.improvement_metrics import ImprovementMetrics
from schemas.sandbox import SandboxSession
from schemas.trace import NormalizedTrace
from services.trace_analyzer_service import (
    TraceAnalyzerRequest,
    TraceAnalyzerService,
)


class FakeLangfuseTraceService:
    def __init__(self, traces: list[NormalizedTrace], steps: list[str]) -> None:
        self._traces = traces
        self._steps = steps

    def fetch_traces(self, filters):
        self._steps.append("fetch")
        assert filters.trace_ids == ["trace-1"]
        assert filters.limit == 5
        return self._traces


class FakeTraceStorageService:
    def __init__(self, loaded_traces: list[NormalizedTrace], steps: list[str]) -> None:
        self._loaded_traces = loaded_traces
        self._steps = steps
        self.saved_traces: list[NormalizedTrace] = []

    def save_traces(self, traces: list[NormalizedTrace]) -> int:
        self._steps.append("save")
        self.saved_traces = traces
        return len(traces)

    def load_traces(self, query):
        self._steps.append("load")
        assert query.run_id == "run-123"
        return self._loaded_traces


class FakeSandboxService:
    def __init__(self, steps: list[str]) -> None:
        self._steps = steps
        self.last_session: SandboxSession | None = None

    def create_sandbox(self, request):
        self._steps.append("create_sandbox")
        self.last_session = SandboxSession(
            sandbox_id="sandbox-1",
            sandbox_path="/tmp/sandbox-1",
            repo_path="/tmp/sandbox-1/repo",
            target_repo_url=request.target_repo_url or "https://example.com/default.git",
        )
        return self.last_session

    def teardown_sandbox(self, session: SandboxSession) -> None:
        self._steps.append("teardown_sandbox")
        assert self.last_session is not None
        assert session.sandbox_path == self.last_session.sandbox_path


class FakeImprovementMetricsService:
    def __init__(self, steps: list[str]) -> None:
        self._steps = steps

    def measure_improvement(self, request, *, between_runs=None) -> ImprovementMetrics:
        assert request.baseline.command == ["uv", "run", "pytest"]
        self._steps.append("measure_baseline")
        if between_runs is not None:
            between_runs()
        self._steps.append("measure_post_change")
        return ImprovementMetrics.model_validate(
            {
                "baseline": {
                    "command": ["uv", "run", "pytest"],
                    "cwd": None,
                    "timeout_seconds": 900,
                    "exit_code": 1,
                    "success": False,
                    "duration_ms": 100,
                    "tests_passed": 2,
                    "tests_failed": 1,
                    "tests_skipped": 0,
                    "stdout_excerpt": "",
                    "stderr_excerpt": "",
                },
                "post_change": {
                    "command": ["uv", "run", "pytest"],
                    "cwd": None,
                    "timeout_seconds": 900,
                    "exit_code": 0,
                    "success": True,
                    "duration_ms": 90,
                    "tests_passed": 3,
                    "tests_failed": 0,
                    "tests_skipped": 0,
                    "stdout_excerpt": "",
                    "stderr_excerpt": "",
                },
                "delta": {
                    "exit_code_delta": -1,
                    "success_delta": 1,
                    "tests_passed_delta": 1,
                    "tests_failed_delta": -1,
                    "tests_skipped_delta": 0,
                    "score_before": 1,
                    "score_after": 3,
                    "score_delta": 2,
                },
                "improved": True,
            }
        )


def test_trace_analyzer_orchestrates_fetch_store_analyze_and_synthesize_in_order() -> None:
    steps: list[str] = []
    fetched_trace = NormalizedTrace(trace_id="trace-1")
    loaded_trace = NormalizedTrace(trace_id="trace-1", run_id="run-123")

    langfuse_trace_service = FakeLangfuseTraceService([fetched_trace], steps)
    trace_storage_service = FakeTraceStorageService([loaded_trace], steps)
    sandbox_service = FakeSandboxService(steps)

    def graph_builder(*, trace_storage_service, sandbox_service):
        steps.append("build_graph")

        class FakeGraph:
            def invoke(self, state):
                steps.append("graph_invoke")
                assert state["run_id"] == "run-123"
                assert state["sandbox_path"] == "/tmp/sandbox-1"
                return {
                    "harness_change_set": HarnessChangeSet(
                        run_id="run-123",
                        trace_ids=["trace-1"],
                        summary="Synthesized one harness change.",
                        harness_changes=[],
                    ).model_dump(mode="json")
                }

        return FakeGraph()

    service = TraceAnalyzerService(
        langfuse_trace_service=langfuse_trace_service,
        trace_storage_service=trace_storage_service,
        sandbox_service=sandbox_service,
        graph_builder=graph_builder,
    )

    result = service.analyze(
        TraceAnalyzerRequest(
            run_id="run-123",
            target_repo_url="https://example.com/repo.git",
            trace_ids=["trace-1"],
            limit=5,
            from_timestamp=datetime(2026, 3, 6, tzinfo=timezone.utc),
        )
    )

    assert steps == [
        "fetch",
        "save",
        "load",
        "create_sandbox",
        "build_graph",
        "graph_invoke",
        "teardown_sandbox",
    ]
    assert len(trace_storage_service.saved_traces) == 1
    assert trace_storage_service.saved_traces[0].run_id == "run-123"
    assert result.run_id == "run-123"
    assert result.target_repo_url == "https://example.com/repo.git"
    assert result.trace_ids == ["trace-1"]
    assert result.fetched_trace_count == 1
    assert result.persisted_trace_count == 1
    assert result.loaded_trace_count == 1
    assert result.harness_change_set.summary == "Synthesized one harness change."
    assert result.improvement_metrics is None


def test_trace_analyzer_runs_boosting_metrics_when_evaluation_command_is_provided() -> None:
    steps: list[str] = []
    trace = NormalizedTrace(trace_id="trace-1", run_id="run-123")

    langfuse_trace_service = FakeLangfuseTraceService([trace], steps)
    trace_storage_service = FakeTraceStorageService([trace], steps)
    sandbox_service = FakeSandboxService(steps)
    metrics_service = FakeImprovementMetricsService(steps)

    def graph_builder(*, trace_storage_service, sandbox_service):
        del trace_storage_service, sandbox_service
        steps.append("build_graph")

        class FakeGraph:
            def invoke(self, state):
                steps.append("graph_invoke")
                assert state["run_id"] == "run-123"
                return {
                    "harness_change_set": HarnessChangeSet(
                        run_id="run-123",
                        trace_ids=["trace-1"],
                        summary="Synthesized one harness change after boosting.",
                        harness_changes=[],
                    ).model_dump(mode="json")
                }

        return FakeGraph()

    service = TraceAnalyzerService(
        langfuse_trace_service=langfuse_trace_service,
        trace_storage_service=trace_storage_service,
        sandbox_service=sandbox_service,
        improvement_metrics_service=metrics_service,
        graph_builder=graph_builder,
    )

    result = service.analyze(
        TraceAnalyzerRequest(
            run_id="run-123",
            trace_ids=["trace-1"],
            limit=5,
            evaluation_command=["uv", "run", "pytest"],
        )
    )

    assert steps == [
        "fetch",
        "save",
        "load",
        "create_sandbox",
        "measure_baseline",
        "build_graph",
        "graph_invoke",
        "measure_post_change",
        "teardown_sandbox",
    ]
    assert result.harness_change_set.summary == "Synthesized one harness change after boosting."
    assert result.improvement_metrics is not None
    assert result.improvement_metrics.improved is True
