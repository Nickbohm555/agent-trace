from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from models import Base
from schemas.trace import NormalizedTrace, NormalizedTraceError, NormalizedTraceSpan, TraceStorageQuery
from services.trace_storage_service import TraceStorageService


def build_service() -> tuple[TraceStorageService, sessionmaker[Session]]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return TraceStorageService(session_factory=session_factory), session_factory


def test_save_and_load_traces_round_trip() -> None:
    service, _ = build_service()
    trace = NormalizedTrace(
        trace_id="trace-1",
        run_id="run-1",
        name="exp-a",
        environment="dev",
        start_time=datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 3, 6, 12, 0, 1, tzinfo=timezone.utc),
        input_payload={"task": "analyze"},
        output_payload={"status": "done"},
        tags=["deep-agent"],
        metadata={"source": "test"},
        total_tokens=50,
        prompt_tokens=40,
        completion_tokens=10,
        cost_usd=0.002,
        error=NormalizedTraceError(message="trace error", error_type="RuntimeError"),
        spans=[
            NormalizedTraceSpan(
                span_id="span-1",
                name="tool_call",
                input_payload={"tool": "read_trace", "arg": 1},
                output_payload={"ok": True},
                error=NormalizedTraceError(message="span error", error_type="ValueError"),
            )
        ],
    )

    persisted = service.save_traces([trace], raw_payload_by_trace_id={"trace-1": {"raw": True}})

    assert persisted == 1

    loaded = service.load_traces(TraceStorageQuery(run_id="run-1"))
    assert len(loaded) == 1
    assert loaded[0].trace_id == "trace-1"
    assert loaded[0].experiment_name == "exp-a"
    assert len(loaded[0].spans) == 1
    assert loaded[0].tool_calls[0]["name"] == "read_trace"
    assert len(loaded[0].errors) == 2
    assert loaded[0].raw_payload == {"raw": True}


def test_save_traces_upserts_existing_trace_id() -> None:
    service, _ = build_service()
    first = NormalizedTrace(trace_id="trace-2", run_id="run-2", name="exp-a")
    second = NormalizedTrace(trace_id="trace-2", run_id="run-2", name="exp-b")

    service.save_traces([first])
    service.save_traces([second])

    loaded = service.load_traces(TraceStorageQuery(trace_ids=["trace-2"]))
    assert len(loaded) == 1
    assert loaded[0].experiment_name == "exp-b"


def test_load_traces_filters_by_experiment() -> None:
    service, _ = build_service()
    service.save_traces(
        [
            NormalizedTrace(trace_id="trace-3", run_id="run-3", name="experiment-x"),
            NormalizedTrace(trace_id="trace-4", run_id="run-3", name="experiment-y"),
        ]
    )

    loaded = service.load_traces(TraceStorageQuery(experiment_name="experiment-y"))

    assert len(loaded) == 1
    assert loaded[0].trace_id == "trace-4"
