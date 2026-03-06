from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Callable

from schemas.improvement_metrics import EvaluationRunMetrics, ImprovementDelta, ImprovementMetrics
from schemas.sandbox import SandboxCommandRequest, SandboxSession
from services.sandbox_service import SandboxService

logger = logging.getLogger(__name__)

_TEST_COUNT_PATTERNS = {
    "tests_passed": re.compile(r"(?P<count>\d+)\s+passed\b", re.IGNORECASE),
    "tests_failed": re.compile(r"(?P<count>\d+)\s+failed\b", re.IGNORECASE),
    "tests_skipped": re.compile(r"(?P<count>\d+)\s+skipped\b", re.IGNORECASE),
}


@dataclass(frozen=True)
class EvaluationCommandConfig:
    command: list[str]
    cwd: str | None = None
    timeout_seconds: int = 900


@dataclass(frozen=True)
class ImprovementMetricsRequest:
    sandbox_session: SandboxSession
    baseline: EvaluationCommandConfig
    post_change: EvaluationCommandConfig | None = None


@dataclass
class ImprovementMetricsService:
    sandbox_service: SandboxService
    output_excerpt_chars: int = 1000

    def measure_improvement(
        self,
        request: ImprovementMetricsRequest,
        *,
        between_runs: Callable[[], None] | None = None,
    ) -> ImprovementMetrics:
        logger.info(
            "Starting improvement metrics run",
            extra={
                "sandbox_id": request.sandbox_session.sandbox_id,
                "baseline_command": request.baseline.command,
                "post_change_command": (request.post_change or request.baseline).command,
            },
        )
        baseline_metrics = self._run_and_extract_metrics(
            session=request.sandbox_session,
            command_config=request.baseline,
        )
        if between_runs is not None:
            between_runs()
        post_change_metrics = self._run_and_extract_metrics(
            session=request.sandbox_session,
            command_config=request.post_change or request.baseline,
        )

        improvement_metrics = self._build_improvement_metrics(
            baseline=baseline_metrics,
            post_change=post_change_metrics,
        )
        logger.info(
            "Completed improvement metrics run",
            extra={
                "sandbox_id": request.sandbox_session.sandbox_id,
                "baseline_exit_code": baseline_metrics.exit_code,
                "post_change_exit_code": post_change_metrics.exit_code,
                "tests_passed_delta": improvement_metrics.delta.tests_passed_delta,
                "tests_failed_delta": improvement_metrics.delta.tests_failed_delta,
                "improved": improvement_metrics.improved,
            },
        )
        return improvement_metrics

    def _run_and_extract_metrics(
        self,
        *,
        session: SandboxSession,
        command_config: EvaluationCommandConfig,
    ) -> EvaluationRunMetrics:
        started_at = time.perf_counter()
        command_result = self.sandbox_service.run_command(
            session,
            SandboxCommandRequest(
                command=command_config.command,
                cwd=command_config.cwd,
                timeout_seconds=command_config.timeout_seconds,
            ),
        )
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        parsed_counts = self._parse_test_counts(
            stdout=command_result.stdout,
            stderr=command_result.stderr,
        )
        return EvaluationRunMetrics(
            command=command_config.command,
            cwd=command_config.cwd,
            timeout_seconds=command_config.timeout_seconds,
            exit_code=command_result.exit_code,
            success=command_result.exit_code == 0,
            duration_ms=duration_ms,
            tests_passed=parsed_counts["tests_passed"],
            tests_failed=parsed_counts["tests_failed"],
            tests_skipped=parsed_counts["tests_skipped"],
            stdout_excerpt=command_result.stdout[: self.output_excerpt_chars],
            stderr_excerpt=command_result.stderr[: self.output_excerpt_chars],
        )

    @staticmethod
    def _parse_test_counts(*, stdout: str, stderr: str) -> dict[str, int | None]:
        combined_output = "\n".join([stdout, stderr])
        parsed: dict[str, int | None] = {}
        for field_name, pattern in _TEST_COUNT_PATTERNS.items():
            match = pattern.search(combined_output)
            parsed[field_name] = int(match.group("count")) if match else None
        return parsed

    @staticmethod
    def _build_improvement_metrics(
        *,
        baseline: EvaluationRunMetrics,
        post_change: EvaluationRunMetrics,
    ) -> ImprovementMetrics:
        tests_passed_delta = _delta_or_none(baseline.tests_passed, post_change.tests_passed)
        tests_failed_delta = _delta_or_none(baseline.tests_failed, post_change.tests_failed)
        tests_skipped_delta = _delta_or_none(baseline.tests_skipped, post_change.tests_skipped)
        score_before = _score(baseline)
        score_after = _score(post_change)
        score_delta = _delta_or_none(score_before, score_after)

        delta = ImprovementDelta(
            exit_code_delta=post_change.exit_code - baseline.exit_code,
            success_delta=int(post_change.success) - int(baseline.success),
            tests_passed_delta=tests_passed_delta,
            tests_failed_delta=tests_failed_delta,
            tests_skipped_delta=tests_skipped_delta,
            score_before=score_before,
            score_after=score_after,
            score_delta=score_delta,
        )
        improved = False
        if score_delta is not None:
            improved = score_delta > 0
        elif delta.success_delta != 0:
            improved = delta.success_delta > 0
        else:
            improved = delta.exit_code_delta < 0

        return ImprovementMetrics(
            baseline=baseline,
            post_change=post_change,
            delta=delta,
            improved=improved,
        )


def _delta_or_none(before: int | None, after: int | None) -> int | None:
    if before is None or after is None:
        return None
    return after - before


def _score(metrics: EvaluationRunMetrics) -> int | None:
    if metrics.tests_passed is None and metrics.tests_failed is None:
        return None
    return (metrics.tests_passed or 0) - (metrics.tests_failed or 0)
