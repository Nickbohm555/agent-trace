from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, Mapping, cast

ReasoningLevel = Literal["low", "medium", "high", "xhigh"]
ReasoningPhase = Literal["planning", "implementation", "verification"]

_VALID_REASONING_LEVELS: set[str] = {"low", "medium", "high", "xhigh"}
_VALID_PHASES: set[str] = {"planning", "implementation", "verification"}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TracerReasoningConfig:
    """Phase-aware reasoning settings for tracer runs."""

    default_level: ReasoningLevel = "high"
    phase_levels: dict[ReasoningPhase, ReasoningLevel] = field(
        default_factory=lambda: {
            "planning": "xhigh",
            "implementation": "high",
            "verification": "xhigh",
        }
    )

    def level_for_phase(self, phase: ReasoningPhase) -> ReasoningLevel:
        """Return the effective level for a phase, falling back to default."""
        return self.phase_levels.get(phase, self.default_level)

    @classmethod
    def from_run_config(cls, run_config: Mapping[str, object] | None) -> TracerReasoningConfig:
        """Build config from optional run overrides, preserving safe defaults."""
        if not run_config:
            return cls()

        default_level = _coerce_reasoning_level(run_config.get("reasoning_level"), fallback="high")
        phase_levels = _merge_phase_levels(
            base={
                "planning": "xhigh",
                "implementation": "high",
                "verification": "xhigh",
            },
            override=run_config.get("reasoning_phase_levels"),
            default_level=default_level,
        )

        return cls(default_level=default_level, phase_levels=phase_levels)


def resolve_reasoning_phase(raw_phase: object) -> ReasoningPhase:
    if isinstance(raw_phase, str) and raw_phase in _VALID_PHASES:
        return cast(ReasoningPhase, raw_phase)
    if raw_phase is not None:
        logger.warning("Invalid reasoning phase provided; defaulting to planning", extra={"phase": raw_phase})
    return "planning"


def resolve_reasoning_level(raw_level: object, fallback: ReasoningLevel) -> ReasoningLevel:
    return _coerce_reasoning_level(raw_level, fallback=fallback)


def _coerce_reasoning_level(raw_level: object, fallback: ReasoningLevel) -> ReasoningLevel:
    if isinstance(raw_level, str) and raw_level in _VALID_REASONING_LEVELS:
        return cast(ReasoningLevel, raw_level)
    if raw_level is not None:
        logger.warning(
            "Invalid reasoning level provided; using fallback",
            extra={"reasoning_level": raw_level, "fallback": fallback},
        )
    return fallback


def _merge_phase_levels(
    base: dict[ReasoningPhase, ReasoningLevel],
    override: object,
    default_level: ReasoningLevel,
) -> dict[ReasoningPhase, ReasoningLevel]:
    merged = dict(base)
    if not isinstance(override, Mapping):
        return merged

    for raw_phase, raw_level in override.items():
        if not isinstance(raw_phase, str) or raw_phase not in _VALID_PHASES:
            logger.warning("Ignoring invalid reasoning phase override", extra={"phase": raw_phase})
            continue
        merged[cast(ReasoningPhase, raw_phase)] = _coerce_reasoning_level(raw_level, fallback=default_level)

    return merged
