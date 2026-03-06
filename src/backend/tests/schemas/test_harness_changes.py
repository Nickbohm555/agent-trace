from __future__ import annotations

from pydantic import ValidationError

from schemas.harness_changes import (
    HarnessChange,
    HarnessChangeSet,
    SuggestedConfigChange,
    SuggestedPromptEdit,
    SuggestedToolChange,
)


def test_harness_change_set_serializes_machine_readable_payload() -> None:
    change_set = HarnessChangeSet(
        run_id="run-123",
        trace_ids=["trace-a", "trace-b"],
        summary="Improve verification reliability.",
        harness_changes=[
            HarnessChange(
                change_id="prompt-1",
                title="Tighten verification checklist",
                category="prompt",
                confidence=0.91,
                prompt_edit=SuggestedPromptEdit(
                    target="verification_prompt",
                    action="append",
                    instruction="Require tool output assertions before completion.",
                    rationale="Recent traces skipped validation after edits.",
                    expected_outcome="Fewer false-positive completions.",
                ),
            ),
            HarnessChange(
                change_id="tool-1",
                title="Add db schema inspection tool",
                category="tool",
                tool_change=SuggestedToolChange(
                    tool_name="describe_schema",
                    action="add",
                    change_summary="Expose read-only schema introspection for worker analyzers.",
                    rationale="Workers lacked direct DB schema visibility.",
                    interface={"args": ["table_name"], "returns": "columns"},
                ),
            ),
            HarnessChange(
                change_id="config-1",
                title="Increase command timeout",
                category="config",
                config_change=SuggestedConfigChange(
                    key="SANDBOX_COMMAND_TIMEOUT_SECONDS",
                    action="increase",
                    value=180,
                    scope="sandbox",
                    rationale="Build/test steps exceeded the old timeout.",
                ),
            ),
        ],
    )

    dumped = change_set.model_dump(mode="json")
    assert dumped["run_id"] == "run-123"
    assert dumped["harness_changes"][0]["category"] == "prompt"
    assert dumped["harness_changes"][1]["tool_change"]["tool_name"] == "describe_schema"
    assert dumped["harness_changes"][2]["config_change"]["scope"] == "sandbox"


def test_harness_change_requires_matching_category_payload() -> None:
    try:
        HarnessChange(
            change_id="bad-1",
            title="Missing payload",
            category="tool",
            confidence=0.6,
        )
    except ValidationError as exc:
        assert "requires the matching payload field" in str(exc)
    else:
        raise AssertionError("Expected ValidationError for missing category payload")


def test_harness_change_rejects_mismatched_category_payload() -> None:
    try:
        HarnessChange(
            change_id="bad-2",
            title="Wrong payload",
            category="config",
            prompt_edit=SuggestedPromptEdit(
                instruction="Do something",
                rationale="Because",
            ),
        )
    except ValidationError as exc:
        assert "cannot include payload for 'prompt'" in str(exc)
    else:
        raise AssertionError("Expected ValidationError for mismatched payload")
