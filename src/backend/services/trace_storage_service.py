from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, sessionmaker

from models import TraceRecord, TraceSpanRecord
from schemas.trace import (
    NormalizedTrace,
    NormalizedTraceError,
    NormalizedTraceSpan,
    StoredTrace,
    TraceStorageQuery,
)

logger = logging.getLogger(__name__)


@dataclass
class TraceStorageService:
    """Persist and load normalized traces for tracer analysis."""

    session_factory: sessionmaker[Session]

    def save_traces(
        self,
        traces: list[NormalizedTrace],
        *,
        raw_payload_by_trace_id: dict[str, dict[str, Any]] | None = None,
    ) -> int:
        if not traces:
            logger.info("No traces provided for persistence")
            return 0

        persisted_count = 0
        with self.session_factory() as session:
            for trace in traces:
                raw_payload = (raw_payload_by_trace_id or {}).get(trace.trace_id)
                existing = session.scalar(
                    select(TraceRecord).where(TraceRecord.trace_id == trace.trace_id)
                )
                if existing is None:
                    record = TraceRecord(trace_id=trace.trace_id)
                    session.add(record)
                else:
                    record = existing
                    record.spans.clear()

                record.run_id = trace.run_id
                record.experiment_name = trace.name
                record.environment = trace.environment
                record.start_time = trace.start_time
                record.end_time = trace.end_time
                record.latency_ms = trace.latency_ms
                record.input_payload = trace.input_payload
                record.output_payload = trace.output_payload
                record.tags = trace.tags
                record.trace_metadata = trace.metadata
                record.total_tokens = trace.total_tokens
                record.prompt_tokens = trace.prompt_tokens
                record.completion_tokens = trace.completion_tokens
                record.cost_usd = trace.cost_usd
                record.raw_payload = raw_payload

                record.tool_calls = self._extract_tool_calls(trace.spans)
                record.errors = self._extract_errors(trace)

                for span in trace.spans:
                    tool_call = self._extract_span_tool_call(span)
                    span_record = TraceSpanRecord(
                        span_id=span.span_id,
                        name=span.name,
                        start_time=span.start_time,
                        end_time=span.end_time,
                        latency_ms=span.latency_ms,
                        status_message=span.status_message,
                        input_payload=span.input_payload,
                        output_payload=span.output_payload,
                        tool_call=tool_call,
                        error_message=span.error.message if span.error else None,
                        error_type=span.error.error_type if span.error else None,
                        error_stacktrace=span.error.stacktrace if span.error else None,
                    )
                    record.spans.append(span_record)

                persisted_count += 1

            session.commit()

        logger.info("Persisted traces", extra={"count": persisted_count})
        return persisted_count

    def load_traces(self, query: TraceStorageQuery) -> list[StoredTrace]:
        with self.session_factory() as session:
            stmt: Select[tuple[TraceRecord]] = select(TraceRecord).order_by(TraceRecord.start_time.desc())

            if query.trace_ids:
                stmt = stmt.where(TraceRecord.trace_id.in_(query.trace_ids))
            if query.run_id:
                stmt = stmt.where(TraceRecord.run_id == query.run_id)
            if query.experiment_name:
                stmt = stmt.where(TraceRecord.experiment_name == query.experiment_name)

            records = session.scalars(stmt.limit(query.limit)).all()

            loaded = [
                StoredTrace(
                    trace_id=record.trace_id,
                    run_id=record.run_id,
                    experiment_name=record.experiment_name,
                    environment=record.environment,
                    start_time=record.start_time,
                    end_time=record.end_time,
                    latency_ms=record.latency_ms,
                    input_payload=record.input_payload,
                    output_payload=record.output_payload,
                    tags=record.tags or [],
                    metadata=record.trace_metadata or {},
                    total_tokens=record.total_tokens,
                    prompt_tokens=record.prompt_tokens,
                    completion_tokens=record.completion_tokens,
                    cost_usd=record.cost_usd,
                    tool_calls=record.tool_calls or [],
                    errors=record.errors or [],
                    raw_payload=record.raw_payload,
                    spans=[
                        NormalizedTraceSpan(
                            span_id=span.span_id,
                            name=span.name,
                            start_time=span.start_time,
                            end_time=span.end_time,
                            latency_ms=span.latency_ms,
                            status_message=span.status_message,
                            input_payload=span.input_payload,
                            output_payload=span.output_payload,
                            error=NormalizedTraceError(
                                message=span.error_message,
                                error_type=span.error_type,
                                stacktrace=span.error_stacktrace,
                            )
                            if span.error_message or span.error_type or span.error_stacktrace
                            else None,
                        )
                        for span in sorted(record.spans, key=lambda item: item.created_at)
                    ],
                )
                for record in records
            ]

        logger.info("Loaded persisted traces", extra={"count": len(loaded)})
        return loaded

    @staticmethod
    def _extract_span_tool_call(span: NormalizedTraceSpan) -> dict[str, Any] | None:
        payload = span.input_payload
        if isinstance(payload, dict):
            tool_name = payload.get("tool") or payload.get("tool_name") or payload.get("name")
            if tool_name:
                return {
                    "span_id": span.span_id,
                    "name": tool_name,
                    "input": payload,
                }
        return None

    @classmethod
    def _extract_tool_calls(cls, spans: list[NormalizedTraceSpan]) -> list[dict[str, Any]]:
        tool_calls: list[dict[str, Any]] = []
        for span in spans:
            tool_call = cls._extract_span_tool_call(span)
            if tool_call:
                tool_calls.append(tool_call)
        return tool_calls

    @staticmethod
    def _extract_errors(trace: NormalizedTrace) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        if trace.error:
            errors.append(
                {
                    "scope": "trace",
                    "message": trace.error.message,
                    "error_type": trace.error.error_type,
                    "stacktrace": trace.error.stacktrace,
                }
            )

        for span in trace.spans:
            if not span.error:
                continue
            errors.append(
                {
                    "scope": "span",
                    "span_id": span.span_id,
                    "message": span.error.message,
                    "error_type": span.error.error_type,
                    "stacktrace": span.error.stacktrace,
                }
            )
        return errors
