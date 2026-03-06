# Agent-Trace Implementation Plan

Tasks are in **recommended implementation order** (1…n). Each section = **one context window**. Sections are atomic (one deliverable each).

**Current section to work on:** Section 4.

---

## Section 1: Single error-analysis agent (invokable)

**Single goal:** Implement one invokable error-analysis agent that takes a single `TraceErrorTask` and returns one or more `ErrorAnalysisFinding`s, so it can later be run in parallel per task.

**Details:**
- Add an agent (e.g. small deep-agent or invokable graph) whose input is a `TraceErrorTask` and output is a list of `ErrorAnalysisFinding`. No orchestration or parallel runner in this section.
- Reuse `TraceErrorTask` and `ErrorAnalysisFinding` schemas. The agent may use the same model as the tracer or a cheaper one; document the contract (input/output).
- Keep existing `collect_error_tasks` and rule-based `_default_error_analyzer`; this section adds the agent implementation only.

**Tech stack and dependencies**
- Libraries/packages: deep-agent library (or LangGraph) for the invokable agent; existing `agents.error_analysis_agent`, schemas.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/error_analysis_agent.py | Add invokable error-analysis agent (e.g. `run_error_analysis_agent(task) -> list[ErrorAnalysisFinding]`). |

**How to test:** Unit test: call the agent with one `TraceErrorTask`; assert return is a list of `ErrorAnalysisFinding` (or empty list).

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section 2: Parallel agent execution and state injection

**Single goal:** Run the error-analysis agent in parallel for all tasks from loaded traces and inject the aggregated findings into tracer state.

**Details:**
- Use `collect_error_tasks(traces)` to get tasks; for each task (or batched subset), invoke the error-analysis agent from Section 1; aggregate all findings into one list; set `parallel_error_findings` and `parallel_error_count` in state.
- Wire this path in orchestration or in deep-agent middleware (when run_id is set and traces are loaded). Do not change state schema; only populate it from agent results.
- Optional: keep a fallback to rule-based analyzer for tests or low-cost mode; document both paths.

**Tech stack and dependencies**
- Libraries/packages: Existing error_analysis_agent (Section 1), trace_storage_service, tracer_state.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/error_analysis_agent.py | Add parallel runner that invokes the Section 1 agent per task and aggregates findings. |
| src/backend/agents/deep_agent_tracer.py | Use the parallel agent path (orchestration or middleware) and inject findings into state. |
| src/backend/services/trace_analyzer_service.py | If orchestration runs analysis: load traces, run parallel agent analysis, pass findings in initial state. |

**How to test:** Integration test: persist a failing trace, run tracer with run_id; assert state contains `parallel_error_findings` and `parallel_error_count` produced by the agent path.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section 3: Synthesis tool or step for main tracer agent

**Single goal:** Add one mechanism by which the main tracer agent produces a `HarnessChangeSet` from `parallel_error_findings` (synthesis tool or dedicated synthesis step).

**Details:**
- Implement either: (a) a tool the main agent can call with findings and that returns a proposed `HarnessChangeSet`, or (b) a dedicated synthesis node/step in the graph where the model outputs structured harness changes. Graph result state must include `harness_change_set` and `harness_changes` from this path.
- Reuse `HarnessChangeSet` and schemas from `schemas/harness_changes.py`. Do not remove rule-based synthesis middleware in this section; only add the agent-driven path.

**Tech stack and dependencies**
- Libraries/packages: deep-agent library; existing `schemas.harness_changes`, `agents.tracer_state`.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/deep_agent_tracer.py | Add synthesis tool or synthesis step; write agent-produced harness_change_set into state. |

**How to test:** Unit test: invoke deep-agent with state containing `parallel_error_findings`; assert result state includes `harness_change_set` produced by the model (tool or step), not by middleware.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section 4: Synthesis prompts and removal of rule-based synthesis middleware

**Single goal:** Add synthesis instructions to the main agent and remove or bypass rule-based synthesis middleware so only the main agent produces the harness change set.

**Details:**
- Add prompt text in `tracer_prompts.py` so the main agent knows when and how to produce harness change suggestions from findings (e.g. when to call the synthesis tool or how to fill the synthesis step).
- Remove or bypass `TracerHarnessSynthesisMiddleware` (or equivalent) that calls `synthesize_harness_changes_from_findings`; ensure no code path overwrites the agent-produced `harness_change_set` with rule-based output. Keep or archive `harness_change_synthesis.py` as reference/fallback only if needed.

**Tech stack and dependencies**
- Libraries/packages: None new.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/tracer_prompts.py | Add synthesis instructions for the main agent. |
| src/backend/agents/deep_agent_tracer.py | Remove or bypass rule-based synthesis middleware for harness_change_set. |
| src/backend/agents/harness_change_synthesis.py | Keep as reference/fallback or remove; do not use for primary synthesis path. |

**How to test:** Full tracer run; assert API response `harness_change_set` is produced by the main agent path and not by `synthesize_harness_changes_from_findings`.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section 5: Aggregation step for harness suggestions and feedback

**Single goal:** Add an aggregation step that combines agent-produced harness suggestions with optional external feedback into a single `HarnessChangeSet`-shaped output.

**Details:**
- After the graph returns, run an aggregation function that takes the agent-produced `harness_change_set` and optional feedback (e.g. from a prior run or API payload) and returns a merged/updated `HarnessChangeSet`. Do not change the schema of `HarnessChangeSet`.
- No approval or apply logic in this section; only the aggregation of “suggestions + feedback.”

**Tech stack and dependencies**
- Libraries/packages: None new beyond existing harness schemas.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/services/trace_analyzer_service.py | Run aggregation after graph return; merge suggestions with feedback. |
| src/backend/schemas (or new) | Optional: feedback payload schema for aggregation input. |

**How to test:** Unit test: aggregation merges agent suggestions with feedback and returns a valid `HarnessChangeSet`.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section 6: API for proposed changes and approve/apply (human-in-the-loop)

**Single goal:** Expose an API so proposed harness changes can be reviewed and applied only after approval (or document auto-apply mode).

**Details:**
- Add or extend endpoints: e.g. get proposed harness changes for a run, and approve/apply (or reject). Apply harness changes only when approval is given (or when a documented auto-apply mode is enabled).
- Do not change the shape of `HarnessChangeSet`; only add the flow: propose → (optional human review) → approve/apply or reject.

**Tech stack and dependencies**
- Libraries/packages: None new.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/routers/tracer.py | Endpoints for proposed changes and approve/apply (or reject). |
| src/backend/schemas (or new) | Optional: approval result schema. |

**How to test:** API test: submit tracer run; fetch proposed changes; call approve (or reject); assert apply occurs only on approve. Document auto-apply mode if supported.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section 7: Pre-completion verification and deterministic context

**Single goal:** Document the existing pre-completion verification loop and optionally inject deterministic context (e.g. task spec or trace summary) into the verification checklist so agents verify against the spec.

**Details:**
- `TracerPreCompletionVerificationMiddleware` and build-verify-fix prompts already exist. This section: (1) Document in completed.md or docs how the verification loop works (plan → build → verify → fix; PreCompletionChecklistMiddleware forces a verification turn before exit). (2) Optionally harden by ensuring deterministic context (e.g. `current_trace_summary`, task spec snippet, or run_id) is always available and included in `build_pre_completion_checklist_message` when present in state.
- Do not remove or replace the existing middleware; only document and optionally extend context injection.

**Tech stack and dependencies**
- Libraries/packages: None new.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| completed.md or docs | Document pre-completion verification and build-verify-fix loop. |
| src/backend/agents/tracer_middleware.py | Optional: extend checklist message with deterministic context from state (e.g. task spec). |

**How to test:** Manual or unit test: run tracer, confirm pre-completion checklist is injected when agent would otherwise exit; optionally assert checklist content includes trace/spec context when set in state.

**Test results:** (Add when section is complete.)
- Command and outcome.

---
