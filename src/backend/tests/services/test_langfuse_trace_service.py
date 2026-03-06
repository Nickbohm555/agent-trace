from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from schemas.trace import TraceQueryFilters
from services.langfuse_trace_service import LangfuseTraceService


def test_fetch_traces_by_trace_ids_normalizes_payload() -> None:
    trace_payload = {
        "id": "trace-123",
        "sessionId": "run-55",
        "name": "planner-run",
        "environment": "development",
        "timestamp": "2026-03-06T10:00:00Z",
        "endTime": "2026-03-06T10:00:01Z",
        "input": {"task": "analyze"},
        "output": {"status": "done"},
        "tags": ["deep-agent"],
        "metadata": {"origin": "unit-test"},
        "usage": {"totalTokens": 120, "promptTokens": 100, "completionTokens": 20},
        "totalCost": 0.012,
        "error": {"message": "top-level failure", "type": "RuntimeError"},
        "spans": [
            {
                "id": "span-1",
                "name": "tool_call",
                "startTime": "2026-03-06T10:00:00Z",
                "endTime": "2026-03-06T10:00:00.500000Z",
                "statusMessage": "ok",
                "input": {"tool": "read_trace"},
                "output": {"count": 1},
                "error": {"message": "span warning", "type": "Warning"},
            }
        ],
    }

    calls: list[str] = []

    class FakeClient:
        def get_trace(self, *, id: str) -> dict:
            calls.append(id)
            return trace_payload

    service = LangfuseTraceService(client=FakeClient(), enabled=True)
    traces = service.fetch_traces(TraceQueryFilters(trace_ids=["trace-123"]))

    assert calls == ["trace-123"]
    assert len(traces) == 1
    trace = traces[0]
    assert trace.trace_id == "trace-123"
    assert trace.run_id == "run-55"
    assert trace.name == "planner-run"
    assert trace.total_tokens == 120
    assert trace.prompt_tokens == 100
    assert trace.completion_tokens == 20
    assert trace.cost_usd == 0.012
    assert trace.latency_ms == 1000.0
    assert trace.error is not None
    assert trace.error.message == "top-level failure"
    assert len(trace.spans) == 1
    assert trace.spans[0].span_id == "span-1"
    assert trace.spans[0].latency_ms == 500.0


def test_fetch_traces_uses_listing_filters_and_environment() -> None:
    list_calls: list[dict] = []
    start = datetime(2026, 3, 6, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 3, 6, 1, 0, tzinfo=timezone.utc)

    class FakeClient:
        def list_traces(self, **kwargs):
            list_calls.append(kwargs)
            return SimpleNamespace(
                data=[
                    {
                        "id": "trace-list-1",
                        "timestamp": "2026-03-06T00:10:00Z",
                        "endTime": "2026-03-06T00:10:00.100000Z",
                    }
                ]
            )

    service = LangfuseTraceService(client=FakeClient(), enabled=True, environment="staging")
    traces = service.fetch_traces(
        TraceQueryFilters(
            run_name="experiment-7",
            from_timestamp=start,
            to_timestamp=end,
            limit=10,
        )
    )

    assert len(list_calls) == 1
    assert list_calls[0]["name"] == "experiment-7"
    assert list_calls[0]["environment"] == "staging"
    assert list_calls[0]["limit"] == 10
    assert len(traces) == 1
    assert traces[0].trace_id == "trace-list-1"
    assert traces[0].latency_ms == 100.0


def test_fetch_traces_returns_empty_when_langfuse_disabled() -> None:
    service = LangfuseTraceService(client=object(), enabled=False)
    traces = service.fetch_traces(TraceQueryFilters(run_name="x"))
    assert traces == []
