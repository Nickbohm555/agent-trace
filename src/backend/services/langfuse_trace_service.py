from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Iterable

from schemas.trace import (
    NormalizedTrace,
    NormalizedTraceError,
    NormalizedTraceSpan,
    TraceQueryFilters,
)

logger = logging.getLogger(__name__)


class LangfuseTraceService:
    """Fetch and normalize Langfuse traces for tracer analysis."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        enabled: bool | None = None,
        environment: str | None = None,
    ) -> None:
        self._enabled = enabled if enabled is not None else self._env_enabled()
        self._environment = environment or os.getenv("LANGFUSE_ENVIRONMENT")
        self._client = client

    def fetch_traces(self, filters: TraceQueryFilters) -> list[NormalizedTrace]:
        if not self._enabled:
            logger.info("Langfuse disabled; returning empty trace list")
            return []

        client = self._client or self._build_client()
        if client is None:
            logger.warning("Langfuse client unavailable; returning empty trace list")
            return []

        if filters.trace_ids:
            traces = self._fetch_by_trace_ids(client, filters.trace_ids)
        else:
            traces = self._list_traces(client, filters)

        normalized = [self._normalize_trace(trace) for trace in traces]
        logger.info(
            "Fetched and normalized traces from Langfuse",
            extra={
                "trace_count": len(normalized),
                "run_name": filters.run_name,
                "from_timestamp": filters.from_timestamp.isoformat()
                if filters.from_timestamp
                else None,
                "to_timestamp": filters.to_timestamp.isoformat() if filters.to_timestamp else None,
            },
        )
        return normalized

    def _fetch_by_trace_ids(self, client: Any, trace_ids: Iterable[str]) -> list[Any]:
        get_method = self._resolve_method(client, ("get_trace", "fetch_trace", "trace"))
        traces: list[Any] = []
        for trace_id in trace_ids:
            trace = self._call_method(
                get_method,
                (
                    {"id": trace_id},
                    {"trace_id": trace_id},
                ),
            )
            if trace is not None:
                traces.append(trace)

        logger.info("Fetched Langfuse traces by explicit trace IDs", extra={"count": len(traces)})
        return traces

    def _list_traces(self, client: Any, filters: TraceQueryFilters) -> list[Any]:
        list_method = self._resolve_method(
            client,
            (
                "list_traces",
                "fetch_traces",
                "traces",
            ),
        )
        call_kwargs = {
            "name": filters.run_name,
            "from_timestamp": filters.from_timestamp,
            "to_timestamp": filters.to_timestamp,
            "limit": filters.limit,
            "environment": filters.environment or self._environment,
        }

        traces = self._call_method(
            list_method,
            (
                {
                    "name": call_kwargs["name"],
                    "from_timestamp": self._to_iso(call_kwargs["from_timestamp"]),
                    "to_timestamp": self._to_iso(call_kwargs["to_timestamp"]),
                    "limit": call_kwargs["limit"],
                    "environment": call_kwargs["environment"],
                },
                {
                    "name": call_kwargs["name"],
                    "fromTimestamp": self._to_iso(call_kwargs["from_timestamp"]),
                    "toTimestamp": self._to_iso(call_kwargs["to_timestamp"]),
                    "limit": call_kwargs["limit"],
                    "environment": call_kwargs["environment"],
                },
                {
                    "run_name": call_kwargs["name"],
                    "from_timestamp": self._to_iso(call_kwargs["from_timestamp"]),
                    "to_timestamp": self._to_iso(call_kwargs["to_timestamp"]),
                    "limit": call_kwargs["limit"],
                    "environment": call_kwargs["environment"],
                },
            ),
            default=[],
        )
        logger.info("Listed Langfuse traces", extra={"count": len(traces), "limit": filters.limit})
        return traces

    def _build_client(self) -> Any | None:
        try:
            from langfuse import Langfuse
        except Exception:
            logger.exception("Failed importing Langfuse SDK")
            return None

        try:
            client = Langfuse()
            logger.info("Initialized Langfuse client")
            return client
        except Exception:
            logger.exception("Failed initializing Langfuse client")
            return None

    @staticmethod
    def _env_enabled() -> bool:
        return os.getenv("LANGFUSE_ENABLED", "false").lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _to_iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _resolve_method(client: Any, method_names: tuple[str, ...]) -> Any:
        # SDK versions vary; resolve a supported method and return callable.
        for method_name in method_names:
            method = getattr(client, method_name, None)
            if callable(method):
                return method

        api = getattr(client, "api", None)
        if api is not None:
            trace_api = getattr(api, "trace", None)
            if trace_api is not None:
                for method_name in method_names:
                    method = getattr(trace_api, method_name, None)
                    if callable(method):
                        return method
                list_method = getattr(trace_api, "list", None)
                if callable(list_method):
                    return list_method
                get_method = getattr(trace_api, "get", None)
                if callable(get_method):
                    return get_method

        raise AttributeError(f"No supported Langfuse method found for {method_names}")

    @staticmethod
    def _call_method(method: Any, kwargs_variants: tuple[dict[str, Any], ...], default: Any = None) -> Any:
        for kwargs in kwargs_variants:
            compact = {k: v for k, v in kwargs.items() if v is not None}
            try:
                result = method(**compact)
                return LangfuseTraceService._unwrap_result(result)
            except TypeError:
                continue
        return default

    @staticmethod
    def _unwrap_result(result: Any) -> Any:
        if isinstance(result, list):
            return result
        if result is None:
            return None
        if isinstance(result, dict):
            data = result.get("data")
            if isinstance(data, list):
                return data
            if data is not None:
                return data
            return result

        data_attr = getattr(result, "data", None)
        if isinstance(data_attr, list):
            return data_attr
        if data_attr is not None:
            return data_attr
        return result

    def _normalize_trace(self, trace: Any) -> NormalizedTrace:
        source = self._as_dict(trace)
        spans = [self._normalize_span(span) for span in source.get("spans", []) if span is not None]
        start_time = self._parse_datetime(self._first(source, "timestamp", "startTime", "start_time"))
        end_time = self._parse_datetime(self._first(source, "endTime", "end_time"))
        latency_ms = self._duration_ms(start_time, end_time) or self._coerce_float(
            self._first(source, "latency", "latencyMs", "latency_ms")
        )
        usage = self._as_dict(self._first(source, "usage", "tokenUsage", "token_usage"))
        error = self._normalize_error(self._first(source, "error", "exception"))

        normalized = NormalizedTrace(
            trace_id=str(self._first(source, "id", "traceId", "trace_id")),
            run_id=self._coerce_str(self._first(source, "sessionId", "runId", "run_id", "session_id")),
            name=self._coerce_str(self._first(source, "name")),
            environment=self._coerce_str(self._first(source, "environment", "env")),
            start_time=start_time,
            end_time=end_time,
            latency_ms=latency_ms,
            input_payload=self._first(source, "input"),
            output_payload=self._first(source, "output"),
            tags=self._coerce_tags(self._first(source, "tags")),
            metadata=self._coerce_metadata(self._first(source, "metadata")),
            total_tokens=self._coerce_int(self._first(usage, "totalTokens", "total_tokens")),
            prompt_tokens=self._coerce_int(self._first(usage, "promptTokens", "prompt_tokens")),
            completion_tokens=self._coerce_int(
                self._first(usage, "completionTokens", "completion_tokens")
            ),
            cost_usd=self._coerce_float(self._first(source, "totalCost", "cost", "costUsd", "cost_usd")),
            error=error,
            spans=spans,
        )
        logger.debug(
            "Normalized trace",
            extra={"trace_id": normalized.trace_id, "span_count": len(normalized.spans)},
        )
        return normalized

    def _normalize_span(self, span: Any) -> NormalizedTraceSpan:
        source = self._as_dict(span)
        start_time = self._parse_datetime(self._first(source, "startTime", "start_time", "timestamp"))
        end_time = self._parse_datetime(self._first(source, "endTime", "end_time"))

        return NormalizedTraceSpan(
            span_id=str(self._first(source, "id", "spanId", "span_id")),
            name=self._coerce_str(self._first(source, "name")),
            start_time=start_time,
            end_time=end_time,
            latency_ms=self._duration_ms(start_time, end_time) or self._coerce_float(
                self._first(source, "latency", "latencyMs", "latency_ms")
            ),
            status_message=self._coerce_str(self._first(source, "statusMessage", "status_message", "status")),
            input_payload=self._first(source, "input"),
            output_payload=self._first(source, "output"),
            error=self._normalize_error(self._first(source, "error", "exception")),
        )

    def _normalize_error(self, error: Any) -> NormalizedTraceError | None:
        if error is None:
            return None
        if isinstance(error, str):
            return NormalizedTraceError(message=error)

        source = self._as_dict(error)
        if not source:
            return None
        return NormalizedTraceError(
            message=self._coerce_str(self._first(source, "message", "error")),
            error_type=self._coerce_str(self._first(source, "type", "error_type", "name")),
            stacktrace=self._coerce_str(self._first(source, "stack", "stacktrace")),
        )

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if hasattr(value, "__dict__"):
            return dict(vars(value))
        return {}

    @staticmethod
    def _first(source: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in source and source[key] is not None:
                return source[key]
        return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            value = value.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _duration_ms(start_time: datetime | None, end_time: datetime | None) -> float | None:
        if start_time is None or end_time is None:
            return None
        return max((end_time - start_time).total_seconds() * 1000, 0.0)

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_str(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return str(value)

    @staticmethod
    def _coerce_tags(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value if v is not None]
        return [str(value)]

    @staticmethod
    def _coerce_metadata(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        return {"raw": value}
