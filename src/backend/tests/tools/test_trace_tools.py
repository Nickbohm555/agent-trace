from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from models import Base
from schemas.trace import NormalizedTrace, NormalizedTraceError, NormalizedTraceSpan
from services.trace_storage_service import TraceStorageService
from tools.trace_tools import build_read_trace_tool


def build_service() -> tuple[TraceStorageService, sessionmaker[Session]]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return TraceStorageService(session_factory=session_factory), session_factory


def test_read_trace_tool_requires_filter() -> None:
    service, _ = build_service()
    tool = build_read_trace_tool(service)

    result = tool.invoke({})

    assert "error" in result
    assert result["traces"] == []


def test_read_trace_tool_returns_structured_trace_summary() -> None:
    service, _ = build_service()
    service.save_traces(
        [
            NormalizedTrace(
                trace_id="trace-1",
                run_id="run-1",
                name="exp-1",
                environment="dev",
                start_time=datetime(2026, 3, 6, 10, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 3, 6, 10, 0, 2, tzinfo=timezone.utc),
                latency_ms=2000,
                input_payload={"question": "What failed?"},
                output_payload={"answer": "Tool error."},
                total_tokens=123,
                prompt_tokens=100,
                completion_tokens=23,
                spans=[
                    NormalizedTraceSpan(
                        span_id="span-failed",
                        name="tool.read",
                        status_message="failed: timeout",
                        latency_ms=450,
                        error=NormalizedTraceError(message="timeout", error_type="TimeoutError"),
                    )
                ],
            )
        ]
    )

    tool = build_read_trace_tool(service)
    result = tool.invoke({"run_id": "run-1"})

    assert result["count"] == 1
    assert result["query"]["run_id"] == "run-1"
    assert result["traces"][0]["trace_id"] == "trace-1"
    assert result["traces"][0]["latency_ms"] == 2000
    assert result["traces"][0]["token_usage"]["total_tokens"] == 123
    assert result["traces"][0]["input_payload"] == {"question": "What failed?"}
    assert result["traces"][0]["output_payload"] == {"answer": "Tool error."}
    assert result["traces"][0]["failed_spans"][0]["span_id"] == "span-failed"
