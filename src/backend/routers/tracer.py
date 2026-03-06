from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from db import SessionLocal
from schemas.tracer_api import (
    TracerProposalApprovalRequest,
    TracerProposedChangesResponse,
    TracerProposalStatus,
    TracerRunRequest,
    TracerRunResponse,
)
from services.harness_change_review_service import (
    HarnessChangeProposal,
    HarnessChangeReviewService,
)
from services.langfuse_trace_service import LangfuseTraceService
from services.sandbox_service import SandboxService
from services.trace_analyzer_service import (
    TraceAnalyzerRequest,
    TraceAnalyzerService,
)
from services.trace_storage_service import TraceStorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tracer", tags=["tracer"])
_harness_change_review_service = HarnessChangeReviewService(
    auto_apply_enabled=os.getenv("TRACER_AUTO_APPLY_CHANGES", "").strip().lower()
    in {"1", "true", "yes", "on"}
)


def get_trace_analyzer_service() -> TraceAnalyzerService:
    return TraceAnalyzerService(
        langfuse_trace_service=LangfuseTraceService(),
        trace_storage_service=TraceStorageService(session_factory=SessionLocal),
        sandbox_service=SandboxService(),
    )


def get_harness_change_review_service() -> HarnessChangeReviewService:
    return _harness_change_review_service


def _proposal_to_response(proposal: HarnessChangeProposal) -> TracerProposedChangesResponse:
    return TracerProposedChangesResponse(
        run_id=proposal.run_id,
        status=TracerProposalStatus(proposal.status),
        auto_apply_enabled=proposal.auto_apply_enabled,
        harness_change_set=proposal.harness_change_set,
        approved_at=proposal.approved_at,
        rejected_at=proposal.rejected_at,
        applied_at=proposal.applied_at,
    )


@router.post("/run", response_model=TracerRunResponse)
async def run_tracer(
    payload: TracerRunRequest,
    trace_analyzer_service: TraceAnalyzerService = Depends(get_trace_analyzer_service),
    harness_change_review_service: HarnessChangeReviewService = Depends(get_harness_change_review_service),
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
    proposal = harness_change_review_service.record_proposal(
        run_id=result.run_id,
        harness_change_set=result.harness_change_set,
    )
    logger.info(
        "Stored proposed harness changes for review",
        extra={
            "run_id": result.run_id,
            "proposal_status": proposal.status,
            "proposal_change_count": len(proposal.harness_change_set.harness_changes),
            "auto_apply_enabled": proposal.auto_apply_enabled,
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


@router.get("/{run_id}/proposed-changes", response_model=TracerProposedChangesResponse)
def get_proposed_harness_changes(
    run_id: str,
    harness_change_review_service: HarnessChangeReviewService = Depends(get_harness_change_review_service),
) -> TracerProposedChangesResponse:
    proposal = harness_change_review_service.get_proposal(run_id=run_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"No proposed harness changes found for run_id '{run_id}'.")

    logger.info(
        "Fetched proposed harness changes",
        extra={
            "run_id": run_id,
            "proposal_status": proposal.status,
            "proposal_change_count": len(proposal.harness_change_set.harness_changes),
        },
    )
    return _proposal_to_response(proposal)


@router.post("/{run_id}/approval", response_model=TracerProposedChangesResponse)
def review_proposed_harness_changes(
    run_id: str,
    payload: TracerProposalApprovalRequest,
    harness_change_review_service: HarnessChangeReviewService = Depends(get_harness_change_review_service),
) -> TracerProposedChangesResponse:
    proposal = harness_change_review_service.review_proposal(
        run_id=run_id,
        decision=payload.decision,
        apply=payload.apply,
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"No proposed harness changes found for run_id '{run_id}'.")

    logger.info(
        "Reviewed proposed harness changes through API",
        extra={
            "run_id": run_id,
            "decision": payload.decision,
            "apply": payload.apply,
            "proposal_status": proposal.status,
        },
    )
    return _proposal_to_response(proposal)
