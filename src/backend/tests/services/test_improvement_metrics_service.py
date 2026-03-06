from __future__ import annotations

from schemas.sandbox import SandboxCommandResult, SandboxSession
from services.improvement_metrics_service import (
    EvaluationCommandConfig,
    ImprovementMetricsRequest,
    ImprovementMetricsService,
)


class FakeSandboxService:
    def __init__(self, results: list[SandboxCommandResult]) -> None:
        self._results = results
        self.commands: list[list[str]] = []

    def run_command(self, session: SandboxSession, request) -> SandboxCommandResult:
        del session
        self.commands.append(request.command)
        return self._results.pop(0)


def test_measure_improvement_computes_test_count_deltas_and_score() -> None:
    sandbox_service = FakeSandboxService(
        [
            SandboxCommandResult(
                exit_code=1,
                stdout="================== 2 passed, 1 failed in 0.12s ==================\n",
                stderr="",
            ),
            SandboxCommandResult(
                exit_code=0,
                stdout="================== 3 passed, 0 failed in 0.09s ==================\n",
                stderr="",
            ),
        ]
    )
    service = ImprovementMetricsService(sandbox_service=sandbox_service)
    sandbox_session = SandboxSession(
        sandbox_id="sandbox-1",
        sandbox_path="/tmp/sandbox-1",
        repo_path="/tmp/sandbox-1/repo",
        target_repo_url="https://example.com/repo.git",
    )
    steps: list[str] = []

    result = service.measure_improvement(
        ImprovementMetricsRequest(
            sandbox_session=sandbox_session,
            baseline=EvaluationCommandConfig(command=["uv", "run", "pytest"]),
        ),
        between_runs=lambda: steps.append("between"),
    )

    assert sandbox_service.commands == [["uv", "run", "pytest"], ["uv", "run", "pytest"]]
    assert steps == ["between"]
    assert result.baseline.tests_passed == 2
    assert result.post_change.tests_passed == 3
    assert result.delta.tests_passed_delta == 1
    assert result.delta.tests_failed_delta == -1
    assert result.delta.score_before == 1
    assert result.delta.score_after == 3
    assert result.delta.score_delta == 2
    assert result.improved is True


def test_measure_improvement_handles_commands_without_test_count_output() -> None:
    sandbox_service = FakeSandboxService(
        [
            SandboxCommandResult(exit_code=0, stdout="baseline ok\n", stderr=""),
            SandboxCommandResult(exit_code=2, stdout="", stderr="post-change failed\n"),
        ]
    )
    service = ImprovementMetricsService(sandbox_service=sandbox_service)
    sandbox_session = SandboxSession(
        sandbox_id="sandbox-1",
        sandbox_path="/tmp/sandbox-1",
        repo_path="/tmp/sandbox-1/repo",
        target_repo_url="https://example.com/repo.git",
    )

    result = service.measure_improvement(
        ImprovementMetricsRequest(
            sandbox_session=sandbox_session,
            baseline=EvaluationCommandConfig(command=["sh", "-c", "echo baseline"]),
            post_change=EvaluationCommandConfig(command=["sh", "-c", "exit 2"]),
        )
    )

    assert result.delta.tests_passed_delta is None
    assert result.delta.tests_failed_delta is None
    assert result.delta.score_delta is None
    assert result.delta.exit_code_delta == 2
    assert result.improved is False
