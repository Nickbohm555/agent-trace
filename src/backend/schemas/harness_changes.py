from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChangePriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class SuggestedPromptEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Literal["system_prompt", "planner_prompt", "verification_prompt", "other"] = "system_prompt"
    action: Literal["append", "replace", "remove", "clarify"] = "append"
    instruction: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    expected_outcome: str | None = None


class SuggestedToolChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    action: Literal["add", "update", "remove"]
    change_summary: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    interface: dict[str, Any] = Field(default_factory=dict)
    safety_notes: str | None = None


class SuggestedConfigChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    action: Literal["set", "increase", "decrease", "remove"]
    value: Any | None = None
    scope: Literal["tracer", "sandbox", "runtime", "model", "other"] = "tracer"
    rationale: str = Field(min_length=1)


class HarnessChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    category: Literal["prompt", "tool", "config"]
    priority: ChangePriority = ChangePriority.medium
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    prompt_edit: SuggestedPromptEdit | None = None
    tool_change: SuggestedToolChange | None = None
    config_change: SuggestedConfigChange | None = None

    @model_validator(mode="after")
    def validate_category_payload(self) -> HarnessChange:
        payload_by_category = {
            "prompt": self.prompt_edit,
            "tool": self.tool_change,
            "config": self.config_change,
        }
        for category, payload in payload_by_category.items():
            if category != self.category and payload is not None:
                raise ValueError(f"category '{self.category}' cannot include payload for '{category}'")
        selected_payload = payload_by_category[self.category]
        if selected_payload is None:
            raise ValueError(f"category '{self.category}' requires the matching payload field")
        return self


class HarnessChangeSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str | None = None
    trace_ids: list[str] = Field(default_factory=list)
    summary: str | None = None
    harness_changes: list[HarnessChange] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
