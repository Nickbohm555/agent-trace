from __future__ import annotations

from agents.tracer_prompts import build_tracer_system_prompt


def test_build_tracer_system_prompt_contains_required_plan_build_verify_fix_sections() -> None:
    prompt = build_tracer_system_prompt()

    assert "Planning & Discovery phase" in prompt
    assert "Build phase" in prompt
    assert "Verify phase" in prompt
    assert "Fix phase" in prompt
    assert "Harness synthesis phase" in prompt


def test_build_tracer_system_prompt_requires_spec_based_verification() -> None:
    prompt = build_tracer_system_prompt()

    assert "Validate results against what was asked in the task specification." in prompt
    assert "Compare output to the requested behavior" in prompt
    assert "Never treat \"code looks correct\" as sufficient verification." in prompt


def test_build_tracer_system_prompt_enforces_testable_code_and_exact_paths() -> None:
    prompt = build_tracer_system_prompt()

    assert "evaluated by programmatic tests" in prompt
    assert "Follow file paths from the task specification exactly" in prompt
    assert "edge cases as first-class requirements" in prompt


def test_build_tracer_system_prompt_requires_model_authored_harness_synthesis() -> None:
    prompt = build_tracer_system_prompt()

    assert "parallel_error_findings" in prompt
    assert "Call the `propose_harness_changes` tool exactly once" in prompt
    assert "do not invent changes" in prompt
