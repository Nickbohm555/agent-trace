from __future__ import annotations

from agents.tracer_config import TracerReasoningConfig, resolve_reasoning_phase


def test_tracer_reasoning_config_defaults_to_reasoning_sandwich() -> None:
    config = TracerReasoningConfig()

    assert config.level_for_phase("planning") == "xhigh"
    assert config.level_for_phase("implementation") == "high"
    assert config.level_for_phase("verification") == "xhigh"


def test_tracer_reasoning_config_from_run_config_applies_overrides() -> None:
    config = TracerReasoningConfig.from_run_config(
        {
            "reasoning_level": "medium",
            "reasoning_phase_levels": {
                "implementation": "low",
                "verification": "high",
            },
        }
    )

    assert config.default_level == "medium"
    assert config.level_for_phase("planning") == "xhigh"
    assert config.level_for_phase("implementation") == "low"
    assert config.level_for_phase("verification") == "high"


def test_resolve_reasoning_phase_defaults_invalid_to_planning() -> None:
    assert resolve_reasoning_phase("not-a-real-phase") == "planning"
