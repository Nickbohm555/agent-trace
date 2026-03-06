from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from schemas.harness_changes import (
    HarnessChange,
    HarnessChangeSet,
    SuggestedConfigChange,
    SuggestedPromptEdit,
    SuggestedToolChange,
)

logger = logging.getLogger(__name__)


def synthesize_harness_changes_from_findings(state: Mapping[str, Any]) -> HarnessChangeSet | None:
    """Build a structured HarnessChangeSet from parallel error findings."""
    findings = state.get("parallel_error_findings", [])
    if not findings:
        return None

    grouped_counts: dict[str, int] = {}
    trace_ids: set[str] = set()
    for finding in findings:
        fix_category = str(finding.get("suggested_fix_category") or "unknown")
        grouped_counts[fix_category] = grouped_counts.get(fix_category, 0) + 1
        trace_id = finding.get("trace_id")
        if isinstance(trace_id, str) and trace_id:
            trace_ids.add(trace_id)

    sorted_categories = sorted(
        grouped_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )
    harness_changes: list[HarnessChange] = []

    for index, (fix_category, count) in enumerate(sorted_categories, start=1):
        if fix_category == "timeout_or_retry_policy":
            harness_change = HarnessChange(
                change_id=f"hc-{index:03d}",
                title="Tune execution timeout and retry strategy",
                category="config",
                confidence=0.82,
                config_change=SuggestedConfigChange(
                    key="sandbox.command_timeout_seconds",
                    action="increase",
                    value=180,
                    scope="sandbox",
                    rationale=(
                        f"{count} failing trace(s) indicate timeout-related failures; "
                        "increase timeout to reduce premature command termination."
                    ),
                ),
            )
        elif fix_category in {"schema_contract", "structured_output_format"}:
            harness_change = HarnessChange(
                change_id=f"hc-{index:03d}",
                title="Tighten structured-output schema instructions",
                category="prompt",
                confidence=0.8,
                prompt_edit=SuggestedPromptEdit(
                    target="verification_prompt",
                    action="append",
                    instruction=(
                        "Before finalizing tool or model output, validate it against the expected "
                        "schema and include explicit field-level checks."
                    ),
                    rationale=(
                        f"{count} failing trace(s) show schema/format mismatches; stronger "
                        "verification prompt guidance reduces parse and contract failures."
                    ),
                    expected_outcome="Fewer invalid structured responses and parsing errors.",
                ),
            )
        elif fix_category == "path_resolution":
            harness_change = HarnessChange(
                change_id=f"hc-{index:03d}",
                title="Improve path discovery and file-resolution tooling",
                category="tool",
                confidence=0.76,
                tool_change=SuggestedToolChange(
                    tool_name="read_file",
                    action="update",
                    change_summary=(
                        "Add pre-read path checks and suggested nearest matching files when a "
                        "path is missing."
                    ),
                    rationale=(
                        f"{count} failing trace(s) indicate missing files or bad paths; "
                        "tool-assisted path resolution lowers repeated lookup failures."
                    ),
                    interface={"inputs": ["sandbox_path", "path"], "returns": "content_or_suggestions"},
                ),
            )
        elif fix_category == "environment_permissions":
            harness_change = HarnessChange(
                change_id=f"hc-{index:03d}",
                title="Clarify sandbox execution permissions",
                category="config",
                confidence=0.75,
                config_change=SuggestedConfigChange(
                    key="sandbox.allowed_commands",
                    action="set",
                    value=["pytest", "npm", "uv", "python", "sh"],
                    scope="sandbox",
                    rationale=(
                        f"{count} failing trace(s) indicate permission denials; a clear allowlist "
                        "helps keep execution safe while unblocking expected workflows."
                    ),
                ),
            )
        else:
            harness_change = HarnessChange(
                change_id=f"hc-{index:03d}",
                title="Strengthen plan-build-verify alignment",
                category="prompt",
                confidence=0.65,
                prompt_edit=SuggestedPromptEdit(
                    target="system_prompt",
                    action="append",
                    instruction=(
                        "When root cause is uncertain, explicitly restate assumptions, run one "
                        "targeted diagnostic command, then revise the plan before additional edits."
                    ),
                    rationale=(
                        f"{count} failing trace(s) lacked a specific fix category; a stricter "
                        "diagnostic loop reduces speculative edits."
                    ),
                    expected_outcome="Lower repeat failures from ambiguous root-cause analysis.",
                ),
            )
        harness_changes.append(harness_change)

    summary = (
        "Synthesized harness changes from parallel error analysis; "
        f"{len(findings)} finding(s) across {len(sorted_categories)} fix category(ies)."
    )
    change_set = HarnessChangeSet(
        run_id=state.get("run_id"),
        trace_ids=sorted(trace_ids),
        summary=summary,
        harness_changes=harness_changes,
    )
    logger.info(
        "Synthesized structured harness changes",
        extra={
            "run_id": state.get("run_id"),
            "finding_count": len(findings),
            "change_count": len(harness_changes),
            "categories": [category for category, _ in sorted_categories],
        },
    )
    return change_set
