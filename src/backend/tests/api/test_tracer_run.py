from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from main import app
from routers.tracer import get_trace_analyzer_service
from schemas.harness_changes import HarnessChangeSet
from services.trace_analyzer_service import (
    TraceAnalyzerRequest,
    TraceAnalyzerResult,
)


class FakeTraceAnalyzerService:
    def __init__(self) -> None:
        self.last_request: TraceAnalyzerRequest | None = None

    def analyze(self, request: TraceAnalyzerRequest) -> TraceAnalyzerResult:
        self.last_request = request
        return TraceAnalyzerResult(
            run_id=request.run_id,
            target_repo_url=request.target_repo_url or "https://example.com/default.git",
            trace_ids=request.trace_ids or [],
            fetched_trace_count=3,
            persisted_trace_count=3,
            loaded_trace_count=2,
            harness_change_set=HarnessChangeSet(
                run_id=request.run_id,
                trace_ids=request.trace_ids or [],
                summary="Synthesized one harness change.",
                harness_changes=[],
            ),
        )


def test_run_tracer_endpoint_calls_trace_analyzer_service_and_returns_payload() -> None:
    fake_service = FakeTraceAnalyzerService()
    app.dependency_overrides[get_trace_analyzer_service] = lambda: fake_service
    client = TestClient(app)
    try:
        response = client.post(
            "/api/tracer/run",
            json={
                "run_id": "run-123",
                "target_repo_url": "https://example.com/repo.git",
                "trace_ids": ["trace-1", "trace-2"],
                "from_timestamp": datetime(2026, 3, 6, tzinfo=UTC).isoformat(),
                "limit": 25,
                "max_runtime_seconds": 300,
                "max_steps": 10,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "run-123"
    assert payload["target_repo_url"] == "https://example.com/repo.git"
    assert payload["trace_ids"] == ["trace-1", "trace-2"]
    assert payload["harness_change_set"]["summary"] == "Synthesized one harness change."
    assert fake_service.last_request is not None
    assert fake_service.last_request.run_id == "run-123"
    assert fake_service.last_request.max_runtime_seconds == 300
    assert fake_service.last_request.max_steps == 10


def test_run_tracer_endpoint_accepts_trace_ids_without_explicit_run_id() -> None:
    fake_service = FakeTraceAnalyzerService()
    app.dependency_overrides[get_trace_analyzer_service] = lambda: fake_service
    client = TestClient(app)
    try:
        response = client.post(
            "/api/tracer/run",
            json={
                "trace_ids": ["trace-primary"],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_service.last_request is not None
    assert fake_service.last_request.run_id == "trace-primary"
    assert response.json()["run_id"] == "trace-primary"


def test_run_tracer_endpoint_rejects_missing_run_id_and_trace_ids() -> None:
    client = TestClient(app)
    response = client.post("/api/tracer/run", json={"target_repo_url": "https://example.com/repo.git"})

    assert response.status_code == 422
