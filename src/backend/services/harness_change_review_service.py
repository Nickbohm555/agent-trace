from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Literal

from schemas.harness_changes import HarnessChangeSet

logger = logging.getLogger(__name__)

ProposalDecision = Literal["approve", "reject"]
ProposalStatus = Literal["pending", "approved", "applied", "rejected"]


@dataclass(frozen=True)
class HarnessChangeProposal:
    run_id: str
    status: ProposalStatus
    harness_change_set: HarnessChangeSet
    auto_apply_enabled: bool
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    applied_at: datetime | None = None


class HarnessChangeReviewService:
    """Store and review synthesized harness changes before apply."""

    def __init__(self, *, auto_apply_enabled: bool = False) -> None:
        self._auto_apply_enabled = auto_apply_enabled
        self._proposals: dict[str, HarnessChangeProposal] = {}
        self._lock = Lock()

    def record_proposal(self, *, run_id: str, harness_change_set: HarnessChangeSet) -> HarnessChangeProposal:
        now = datetime.now(UTC)
        normalized_change_set = (
            harness_change_set
            if harness_change_set.run_id == run_id
            else harness_change_set.model_copy(update={"run_id": run_id})
        )
        proposal = HarnessChangeProposal(
            run_id=run_id,
            status="applied" if self._auto_apply_enabled else "pending",
            harness_change_set=normalized_change_set,
            auto_apply_enabled=self._auto_apply_enabled,
            approved_at=now if self._auto_apply_enabled else None,
            rejected_at=None,
            applied_at=now if self._auto_apply_enabled else None,
        )
        with self._lock:
            self._proposals[run_id] = proposal
        logger.info(
            "Recorded proposed harness changes",
            extra={
                "run_id": run_id,
                "status": proposal.status,
                "change_count": len(normalized_change_set.harness_changes),
                "auto_apply_enabled": self._auto_apply_enabled,
            },
        )
        return proposal

    def get_proposal(self, *, run_id: str) -> HarnessChangeProposal | None:
        with self._lock:
            return self._proposals.get(run_id)

    def review_proposal(self, *, run_id: str, decision: ProposalDecision, apply: bool = True) -> HarnessChangeProposal | None:
        with self._lock:
            current = self._proposals.get(run_id)
            if current is None:
                return None

            now = datetime.now(UTC)
            if decision == "reject":
                updated = HarnessChangeProposal(
                    run_id=run_id,
                    status="rejected",
                    harness_change_set=current.harness_change_set,
                    auto_apply_enabled=current.auto_apply_enabled,
                    approved_at=None,
                    rejected_at=now,
                    applied_at=None,
                )
            elif apply:
                updated = HarnessChangeProposal(
                    run_id=run_id,
                    status="applied",
                    harness_change_set=current.harness_change_set,
                    auto_apply_enabled=current.auto_apply_enabled,
                    approved_at=now,
                    rejected_at=None,
                    applied_at=now,
                )
            else:
                updated = HarnessChangeProposal(
                    run_id=run_id,
                    status="approved",
                    harness_change_set=current.harness_change_set,
                    auto_apply_enabled=current.auto_apply_enabled,
                    approved_at=now,
                    rejected_at=None,
                    applied_at=None,
                )
            self._proposals[run_id] = updated

        logger.info(
            "Reviewed proposed harness changes",
            extra={
                "run_id": run_id,
                "decision": decision,
                "apply": apply,
                "status": updated.status,
                "change_count": len(updated.harness_change_set.harness_changes),
            },
        )
        return updated
