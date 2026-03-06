from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import StructuredTool

from schemas.trace import StoredTrace, TraceStorageQuery
from services.trace_storage_service import TraceStorageService

logger = logging.getLogger(__name__)


@dataclass
class ReadTraceTool:
    """Tool adapter that reads persisted traces and returns a compact summary payload."""

    storage_service: TraceStorageService

    def run(
        self,
        *,
        run_id: str | None = None,
        trace_id: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        if run_id is None and trace_id is None:
            logger.warning("read_trace called without run_id or trace_id")
            return {
                "error": "Provide at least one of run_id or trace_id.",
                "query": {"run_id": run_id, "trace_id": trace_id, "limit": limit},
                "traces": [],
            }

        normalized_limit = max(1, min(limit, 50))
        query = TraceStorageQuery(
            run_id=run_id,
            trace_ids=[trace_id] if trace_id else None,
            limit=normalized_limit,
        )
        traces = self.storage_service.load_traces(query)

        logger.info(
            "read_trace completed",
            extra={
                "run_id": run_id,
                "trace_id": trace_id,
                "requested_limit": limit,
                "effective_limit": normalized_limit,
                "trace_count": len(traces),
            },
        )

        return {
            "query": {"run_id": run_id, "trace_id": trace_id, "limit": normalized_limit},
            "count": len(traces),
            "traces": [_summarize_trace(trace) for trace in traces],
        }


def build_read_trace_tool(storage_service: TraceStorageService) -> StructuredTool:
    adapter = ReadTraceTool(storage_service=storage_service)
    return StructuredTool.from_function(
        func=adapter.run,
        name="read_trace",
        description=(
            "Read persisted trace data by run_id or trace_id and return errors, failed spans, "
            "key inputs/outputs, token usage, and latency summary."
        ),
    )


def _summarize_trace(trace: StoredTrace) -> dict[str, Any]:
    span_errors = [
        {
            "span_id": span.span_id,
            "name": span.name,
            "message": span.error.message if span.error else None,
            "error_type": span.error.error_type if span.error else None,
        }
        for span in trace.spans
        if span.error
    ]

    failed_spans = [
        {
            "span_id": span.span_id,
            "name": span.name,
            "status_message": span.status_message,
            "latency_ms": span.latency_ms,
        }
        for span in trace.spans
        if span.error or (span.status_message and "fail" in span.status_message.lower())
    ]

    return {
        "trace_id": trace.trace_id,
        "run_id": trace.run_id,
        "experiment_name": trace.experiment_name,
        "environment": trace.environment,
        "latency_ms": trace.latency_ms,
        "token_usage": {
            "total_tokens": trace.total_tokens,
            "prompt_tokens": trace.prompt_tokens,
            "completion_tokens": trace.completion_tokens,
        },
        "cost_usd": trace.cost_usd,
        "errors": trace.errors,
        "failed_spans": failed_spans,
        "span_errors": span_errors,
        "tool_calls": trace.tool_calls,
        "input_payload": trace.input_payload,
        "output_payload": trace.output_payload,
    }
