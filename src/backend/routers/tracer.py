from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from db import SessionLocal
from schemas.tracer_api import TracerRunRequest, TracerRunResponse
from services.langfuse_trace_service import LangfuseTraceService
from services.sandbox_service import SandboxService
from services.trace_analyzer_service import (
    TraceAnalyzerRequest,
    TraceAnalyzerService,
)
from services.trace_storage_service import TraceStorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tracer", tags=["tracer"])


def get_trace_analyzer_service() -> TraceAnalyzerService:
    return TraceAnalyzerService(
        langfuse_trace_service=LangfuseTraceService(),
        trace_storage_service=TraceStorageService(session_factory=SessionLocal),
        sandbox_service=SandboxService(),
    )


@router.post("/run", response_model=TracerRunResponse)
async def run_tracer(
    payload: TracerRunRequest,
    trace_analyzer_service: TraceAnalyzerService = Depends(get_trace_analyzer_service),
) -> TracerRunResponse:
    resolved_run_id = payload.run_id or (payload.trace_ids[0] if payload.trace_ids else None)
    if resolved_run_id is None:
        raise HTTPException(status_code=422, detail="Provide at least one of run_id or trace_ids.")

    request = TraceAnalyzerRequest(
        run_id=resolved_run_id,
        trace_ids=payload.trace_ids,
        target_repo_url=payload.target_repo_url,
        run_name=payload.run_name,
        from_timestamp=payload.from_timestamp,
        to_timestamp=payload.to_timestamp,
        limit=payload.limit,
        environment=payload.environment,
        evaluation_command=payload.evaluation_command,
        evaluation_cwd=payload.evaluation_cwd,
        evaluation_timeout_seconds=payload.evaluation_timeout_seconds,
        max_runtime_seconds=payload.max_runtime_seconds,
        max_steps=payload.max_steps,
        harness_feedback=payload.harness_feedback,
    )

    logger.info(
        "Received tracer run request",
        extra={
            "run_id": resolved_run_id,
            "trace_id_count": len(payload.trace_ids or []),
            "target_repo_url": payload.target_repo_url,
        },
    )

    try:
        result = await run_in_threadpool(trace_analyzer_service.analyze, request)
    except (ValueError, RuntimeError) as exc:
        logger.warning("Tracer run failed due to invalid request/runtime input", extra={"error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.exception("Tracer run failed with unexpected error")
        raise HTTPException(status_code=500, detail="Failed to execute tracer run.") from exc

    logger.info(
        "Tracer run completed",
        extra={
            "run_id": result.run_id,
            "fetched_trace_count": result.fetched_trace_count,
            "loaded_trace_count": result.loaded_trace_count,
            "change_count": len(result.harness_change_set.harness_changes),
        },
    )

    return TracerRunResponse(
        run_id=result.run_id,
        target_repo_url=result.target_repo_url,
        trace_ids=result.trace_ids,
        fetched_trace_count=result.fetched_trace_count,
        persisted_trace_count=result.persisted_trace_count,
        loaded_trace_count=result.loaded_trace_count,
        harness_change_set=result.harness_change_set,
        improvement_metrics=result.improvement_metrics,
    )
