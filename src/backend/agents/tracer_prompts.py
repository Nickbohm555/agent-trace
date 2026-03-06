from __future__ import annotations

from textwrap import dedent

_PLANNING_AND_DISCOVERY = dedent(
    """
    Planning & Discovery phase:
    - Read the trace context and task specification carefully before changing code.
    - Discover relevant files and existing behavior in the target codebase before implementation.
    - Produce a concrete plan that includes how you will verify success.
    """
).strip()

_BUILD = dedent(
    """
    Build phase:
    - Implement changes with verification in mind so behavior is testable.
    - Reuse existing architecture and functionality where possible.
    - Add or update tests when needed, including happy paths and edge cases.
    """
).strip()

_VERIFY = dedent(
    """
    Verify phase:
    - Execute the relevant test commands and inspect full command output.
    - Validate results against what was asked in the task specification.
    - Never treat "code looks correct" as sufficient verification.
    - Compare output to the requested behavior, not to your own implementation assumptions.
    """
).strip()

_FIX = dedent(
    """
    Fix phase:
    - If verification fails, analyze root cause using errors and test output.
    - Revisit the task specification and adjust implementation until tests pass.
    - Repeat build/verify/fix until the requested behavior is satisfied.
    """
).strip()

_TESTABLE_CODE = dedent(
    """
    Testable Code expectations:
    - Your work is evaluated by programmatic tests, so ensure behavior is verifiable by automated test commands.
    - Follow file paths from the task specification exactly; do not rename files or relocate requested changes.
    - Treat edge cases as first-class requirements, not optional follow-ups to the happy path.
    """
).strip()


def build_tracer_system_prompt() -> str:
    """Return the tracer's plan-build-verify-fix system prompt."""
    return "\n\n".join(
        [
            "You are the tracing deep-agent for harness engineering improvements.",
            _PLANNING_AND_DISCOVERY,
            _BUILD,
            _TESTABLE_CODE,
            _VERIFY,
            _FIX,
        ]
    )
