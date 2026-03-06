# Agent-Trace Implementation Plan

Tasks are in **recommended implementation order** (1…n). Each section = **one context window**.  
Refactor existing implementation into a **deep-agent library in LangGraph**. Sections are atomic (one deliverable each).

**Current section to work on:** Section 13.

**Trace Analyzer alignment gaps (Sections 13–15):** The plan below brings the implementation in line with the described Trace Analyzer Skill flow: parallel error analysis as spawned agents, main agent synthesizes findings, and optional aggregate feedback / human-in-the-loop.

---

## Section 1: Add deep-agent library dependency

**Single goal:** Declare and lock the LangGraph deep-agent library so the tracer can be built with `create_deep_agent` (or equivalent) as the single graph implementation.

**Details:**
- Add the official deep-agent package (e.g. `deepagents` or LangChain/LangGraph deep-agent dependency) to backend dependencies.
- Resolve and lock the dependency (e.g. `uv lock`); ensure no version conflict with existing `langgraph` / `langchain-core`.
- Do not change any tracer code in this section; dependency only.

**Tech stack and dependencies**
- Libraries/packages: Backend – add deep-agent package in `src/backend/pyproject.toml`; refresh `src/backend/uv.lock`.
- Tooling: `uv`; no Docker base image change unless the new dependency requires it.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/pyproject.toml | Add deep-agent dependency. |
| src/backend/uv.lock | Updated lockfile after add. |

**How to test:** Run `docker compose exec backend uv sync` (or equivalent) and confirm no resolution errors; optional `uv run python -c "from deepagents import create_deep_agent"` (or actual package/module name) succeeds.

**Test results:**
- `docker compose exec backend uv sync` -> resolved/audited successfully, no dependency resolution errors.
- `docker compose exec backend uv run python -c "from deepagents import create_deep_agent; print('deepagents import ok (post-rebuild)')"` -> import succeeded.

---

## Section 2: Align tracer state with deep-agent state contract

**Single goal:** Ensure `TracerState` (or the state schema passed to the deep-agent) matches the library’s expected state shape and includes all keys the tracer needs so middleware and orchestration can rely on a single schema.

**Details:**
- Keep or adapt `TracerState` so it is the single state type for the deep-agent graph (e.g. via `state_schema` or equivalent in the library).
- Preserve all existing keys used by orchestration and middleware (messages, run_id, sandbox_path, local_context, reasoning fields, pre_completion_verified, time-budget fields, loop-detection fields, parallel_error_findings, harness_change_set, etc.).
- Remove or replace any use of `add_messages` / LangGraph-specific annotations if the deep-agent library uses a different message reducer; otherwise keep compatibility.

**Tech stack and dependencies**
- Libraries/packages: Existing `langchain-core`, `langgraph`; deep-agent library from Section 1.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/tracer_state.py | Define or adapt TracerState for deep-agent state contract. |
| src/backend/agents/deep_agent_tracer.py | Use the aligned state schema in create_deep_agent / middleware. |

**How to test:** Unit tests that build the deep-agent graph with the state schema and assert initial state and one invocation accept/return the expected keys; no runtime errors.

**Test results:**
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py` -> passed (`9 passed in 2.14s`).

---

## Section 3: Migrate reasoning budget to deep-agent

**Single goal:** Make reasoning compute (phase and level) configurable in the deep-agent path so planning/verification can use higher budget and implementation lower (reasoning sandwich).

**Details:**
- Move reasoning phase/level resolution from `langgraph_agent` into the deep-agent flow (e.g. middleware that sets state or config passed into the model call).
- Use existing `tracer_config` (phase-aware levels, run-level overrides); no change to schema of config, only where it is applied.
- Deep-agent graph must receive and honor reasoning budget when invoking the model.

**Tech stack and dependencies**
- Libraries/packages: deep-agent library; existing `agents.tracer_config`, `agents.tracer_state`.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/tracer_config.py | Keep as-is or minor tweaks for deep-agent use. |
| src/backend/agents/tracer_state.py | Ensure reasoning_phase, reasoning_level, reasoning_phase_levels present. |
| src/backend/agents/deep_agent_tracer.py | Apply reasoning budget (middleware or model-invoke hook) before each model call. |

**How to test:** Unit test: build deep-agent tracer with a mock model; invoke with state that sets reasoning phase/level; assert the model adapter or middleware receives the expected budget (e.g. via spy or callback).

**Test results:**
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py` -> passed (`11 passed in 2.14s`).

---

## Section 4: Migrate pre-completion verification to deep-agent middleware

**Single goal:** Before the tracer can finish, run a verification pass (remind agent to run tests and compare to spec) in the deep-agent path so the agent does not exit without testing.

**Details:**
- Implement pre-completion verification as deep-agent middleware (e.g. `AgentMiddleware` that detects first end-attempt without prior verification and injects a checklist message).
- Reuse logic from `tracer_middleware.py` (should_inject_pre_completion_checklist, build_pre_completion_checklist_message); state must include `pre_completion_verified`.
- Single deliverable: middleware that forces one extra verification turn before completion.

**Tech stack and dependencies**
- Libraries/packages: deep-agent library (middleware API); existing `agents.tracer_middleware`, `agents.tracer_state`.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/tracer_middleware.py | Keep helpers; optionally move injection into a middleware class used by deep-agent. |
| src/backend/agents/deep_agent_tracer.py | Register pre-completion verification middleware in create_deep_agent middleware list. |

**How to test:** Unit test: run deep-agent graph until it would end; assert verification message is injected and one more turn occurs before END; assert `pre_completion_verified` set.

**Test results:**
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py` -> passed (`12 passed in 2.30s`).

---

## Section 5: Migrate time-budget injection to deep-agent middleware

**Single goal:** Inject time-remaining or step-remaining warnings into the tracer’s context in the deep-agent path so the agent shifts to verification and submission under limits.

**Details:**
- Implement time/step budget injection as deep-agent middleware (e.g. `before_agent` or equivalent) using existing logic from `tracer_middleware.apply_time_budget_injection` and `build_time_budget_message`.
- State must include run_started_at_epoch_seconds, max_runtime_seconds, max_steps, agent_step_count, time_budget_notice_interval_steps, time_budget_last_notice_step.
- Middleware appends a system message when conditions are met; no change to API contract.

**Tech stack and dependencies**
- Libraries/packages: deep-agent library; existing `agents.tracer_middleware`, `agents.tracer_state`.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/tracer_middleware.py | Keep time-budget helpers. |
| src/backend/agents/deep_agent_tracer.py | Add time-budget middleware to deep-agent middleware list. |

**How to test:** Unit test: invoke deep-agent with max_steps=1 (or short max_runtime_seconds); assert a budget warning message appears in state/messages and step count is updated.

**Test results:**
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py` -> passed (`13 passed in 2.76s`).

---

## Section 6: Migrate loop-detection to deep-agent middleware

**Single goal:** Track per-file edit counts and, after N edits to the same file, inject a “reconsider your approach” nudge in the deep-agent path to avoid doom loops.

**Details:**
- Implement loop detection as deep-agent middleware that inspects tool calls (e.g. `edit_file`), increments per-file counts in state, and injects a nudge when threshold is reached.
- Reuse logic from `tracer_middleware.apply_loop_detection_injection` and `build_loop_detection_message`; state must include edit_file_counts, loop_detection_threshold, loop_detection_nudged_files.
- Single deliverable: middleware only; no change to tools or API.

**Tech stack and dependencies**
- Libraries/packages: deep-agent library; existing `agents.tracer_middleware`, `agents.tracer_state`.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/tracer_middleware.py | Keep loop-detection helpers. |
| src/backend/agents/deep_agent_tracer.py | Add loop-detection middleware to deep-agent middleware list. |

**How to test:** Unit test: run deep-agent with mock edit_file tool; trigger N edits to same file; assert nudge message is injected and state (edit_file_counts, loop_detection_nudged_files) is updated.

**Test results:**
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py` -> passed (`15 passed in 2.96s`).

---

## Section 7: Migrate parallel error analysis to deep-agent flow

**Single goal:** Run parallel error-analysis workers and inject their findings into deep-agent state so the main agent can use them (Trace Analyzer Skill pattern).

**Details:**
- Load traces by run_id (or trace_ids) via TraceStorageService; run existing `analyze_errors_in_parallel` (error_analysis_agent); inject parallel_error_findings and parallel_error_count into state before or at the start of deep-agent execution.
- Can be done in orchestration (before invoking the graph) or in a deep-agent middleware that runs once when run_id is set and parallel_analysis_completed is false; set parallel_analysis_completed when done.
- No change to HarnessChangeSet schema or synthesis logic in this section; only injection of findings.

**Tech stack and dependencies**
- Libraries/packages: deep-agent library; existing `agents.error_analysis_agent`, `services.trace_storage_service`, `agents.tracer_state`.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/error_analysis_agent.py | Keep as-is; called from orchestration or middleware. |
| src/backend/agents/deep_agent_tracer.py | Either add middleware that runs parallel analysis and injects findings, or document that orchestration must inject them into initial state. |
| src/backend/services/trace_analyzer_service.py | If injection is in orchestration: load traces, run analysis, pass findings in initial state to graph. |

**How to test:** Integration test: persist a failing trace, invoke deep-agent (or orchestration) with run_id; assert state contains parallel_error_findings and parallel_error_count; optionally assert model receives them in next turn.

**Test results:**
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py` -> passed (`17 passed in 3.55s`).
- `docker compose exec backend uv run pytest tests/agents/test_langgraph_agent.py` -> passed (`14 passed in 1.27s`).

---

## Section 8: Migrate harness change synthesis to deep-agent output

**Single goal:** Produce structured HarnessChangeSet from parallel_error_findings in the deep-agent path so the tracer returns harness change suggestions.

**Details:**
- After parallel findings are available, convert them to HarnessChangeSet using existing logic (e.g. _synthesize_harness_changes from langgraph_agent or equivalent); emit harness_change_set and harness_changes in graph result state.
- Can be implemented as a post-agent middleware, a final step in the graph, or in orchestration after graph returns by reading state; choose one and document.
- No change to HarnessChangeSet schema; reuse schemas/harness_changes.py.

**Tech stack and dependencies**
- Libraries/packages: deep-agent library; existing `schemas.harness_changes`, `agents.tracer_state`.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/langgraph_agent.py | Copy or move _synthesize_harness_changes into a shared module or into deep_agent_tracer/orchestration. |
| src/backend/agents/deep_agent_tracer.py | Ensure synthesized harness_change_set is written to state (middleware or wrapper). |
| src/backend/schemas/harness_changes.py | No change; consumed by synthesis. |

**How to test:** Unit or integration test: invoke deep-agent with state containing parallel_error_findings; assert result state includes harness_change_set conforming to HarnessChangeSet; test with no findings and assert no or empty change set.

**Test results:**
- `rg -n "build_tracer_graph|agents\\.langgraph_agent|from agents.langgraph_agent|StateGraph|should_continue" src/backend` -> no matches.
- `docker compose exec backend uv run pytest` -> passed (`59 passed in 4.45s`).
- `docker compose ps` -> `db`, `backend`, `frontend`, `chrome` all `Up` (`db` healthy).
- `curl -s -o /tmp/section10_backend_docs.html -w '%{http_code}\n' http://localhost:8001/docs` -> `200`.
- `curl -s -o /tmp/section10_frontend.html -w '%{http_code}\n' http://localhost:5174` -> `200`.

---

## Section 9: Switch orchestration to deep-agent graph

**Single goal:** TraceAnalyzerService uses build_deep_agent_tracer as the graph builder and invokes it with the same request contract (run_id, sandbox_path, etc.); no code path may call build_tracer_graph for the main tracer.

**Details:**
- Set graph_builder to build_deep_agent_tracer (or a thin wrapper that passes services and returns the same invoke contract).
- _invoke_tracer_graph must pass initial state (run_id, sandbox_path, max_runtime_seconds, max_steps, etc.) and parse result state (harness_change_set) from the deep-agent graph return value.
- Preserve TraceAnalyzerRequest / TraceAnalyzerResult and evaluation (baseline/post-change) flow; only the graph implementation changes.

**Tech stack and dependencies**
- Libraries/packages: deep-agent library; existing trace_analyzer_service, deep_agent_tracer.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/services/trace_analyzer_service.py | Use build_deep_agent_tracer as graph_builder; adapt _invoke_tracer_graph to deep-agent invoke signature and state shape. |
| src/backend/agents/deep_agent_tracer.py | Ensure build_deep_agent_tracer accepts any parameters orchestration needs (e.g. trace_storage_service, sandbox_service). |

**How to test:** Run existing trace_analyzer_service tests; run POST /api/tracer/run with a small run_id; assert 200 and harness_change_set in response.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section 10: Remove legacy LangGraph agent implementation

**Single goal:** Remove or permanently gate the custom StateGraph tracer (build_tracer_graph and its graph nodes) so the codebase has a single implementation path: the deep-agent library.

**Details:**
- Delete or deprecate build_tracer_graph and all graph nodes/edges in langgraph_agent.py that are only used by the legacy path.
- Keep shared pieces used by deep-agent (e.g. _synthesize_harness_changes if moved to a shared module, tracer_state, tracer_config, tracer_prompts, tracer_middleware helpers); remove only the legacy graph construction and routing.
- No new features; deletion/gating only.

**Tech stack and dependencies**
- Libraries/packages: None new.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/langgraph_agent.py | Remove build_tracer_graph, StateGraph, node/edge definitions; keep or relocate shared synthesis/helpers. |

**How to test:** Ensure no imports of build_tracer_graph remain (grep); run full backend test suite and orchestration/API tests; confirm tracer flow still works via deep-agent.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section 11: Update agent tests to deep-agent only

**Single goal:** All agent tests target build_deep_agent_tracer and deep-agent middleware; remove or migrate tests that only exercise build_tracer_graph.

**Details:**
- Migrate or remove tests from test_langgraph_agent.py that assert legacy graph behavior; add or extend tests in test_deep_agent_tracer.py for equivalent coverage (routing, tools, middleware, synthesis, state).
- Test suite must not depend on build_tracer_graph; all tracer behavior validated through build_deep_agent_tracer.
- Preserve coverage for system prompt, tools, local context, sandbox scope, pre-completion, time budget, loop detection, parallel analysis, harness synthesis.

**Tech stack and dependencies**
- Libraries/packages: None new.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/tests/agents/test_langgraph_agent.py | Remove or migrate to test_deep_agent_tracer; delete file if empty. |
| src/backend/tests/agents/test_deep_agent_tracer.py | Add or extend tests for all migrated behaviors. |
| src/backend/tests/agents/test_tracer_middleware.py | Update to run against deep-agent graph if they currently use build_tracer_graph. |

**How to test:** Run pytest for agents and middleware; all tests pass; no references to build_tracer_graph in tests.

**Test results:**
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py tests/agents/test_tracer_middleware.py` -> passed (`24 passed in 3.74s`).
- `rg -n "build_tracer_graph" src/backend/tests` -> no matches.

---

## Section 12: Verify API and UI with deep-agent backend

**Single goal:** Confirm POST /api/tracer/run and the frontend tracer run form and results UI work correctly with the deep-agent-backed orchestration; fix any contract or behavior regressions.

**Details:**
- Manually or via E2E test: submit a tracer run from the UI; assert completion and display of harness change summary (or “no changes”); assert error display on failure.
- Verify response shape (harness_change_set, improvement_metrics) matches frontend types; no breaking change to API response schema.
- Document any intentional contract change; otherwise ensure parity with pre-refactor behavior.

**Tech stack and dependencies**
- Libraries/packages: None new.
- Tooling: Optional E2E or browser test; manual verification acceptable.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/routers/tracer.py | No change unless response shape must be adapted. |
| src/frontend/src/utils/api.ts | Align types with backend response if needed. |
| src/frontend/src/App.tsx | No change unless display logic must be fixed. |

**How to test:** Start stack; open UI; trigger tracer run with run_id; verify success/error and harness change/metrics display; run frontend unit tests and typecheck.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section 13: Parallel error analysis as spawned agents

**Single goal:** Replace parallel error-analysis functions with spawned agents (e.g. deep-agent subagents or invokable agents) so each error is analyzed by an agent, not by the rule-based `_default_error_analyzer`.

**Details:**
- Today: `collect_error_tasks()` + `analyze_errors_in_parallel()` with `AnalyzerFn` (default: keyword-based). No agent spawning.
- Target: For each `TraceErrorTask` (or batched subset), spawn an error-analysis agent (e.g. via deep-agent subagent or a small invokable agent) that produces one or more `ErrorAnalysisFinding`; orchestration runs these in parallel and aggregates findings.
- Keep `ErrorAnalysisFinding` and `TraceErrorTask` schemas; keep injection of `parallel_error_findings` / `parallel_error_count` into tracer state. Only the implementation of “who does the analysis” changes from function to agent(s).
- Preserve optional fallback to the existing rule-based analyzer for tests or low-cost mode if desired; document the two paths.

**Tech stack and dependencies**
- Libraries/packages: deep-agent library (for subagent spawning if used); existing `agents.error_analysis_agent`, `agents.tracer_state`, `schemas` for findings/tasks.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/error_analysis_agent.py | Introduce agent-based analysis path: spawn or invoke error-analysis agents per task (or batch); aggregate findings; keep `collect_error_tasks` and optional rule-based analyzer. |
| src/backend/agents/deep_agent_tracer.py | Call the new agent-based parallel analysis (orchestration or middleware) instead of `analyze_errors_in_parallel` with default analyzer; state injection unchanged. |
| src/backend/services/trace_analyzer_service.py | If orchestration runs analysis: use agent-based analysis when loading traces and building initial state. |

**How to test:** Unit test: run agent-based error analysis on a small set of `TraceErrorTask`s; assert returned list of `ErrorAnalysisFinding` and parallel execution. Integration test: tracer run with run_id; assert state contains `parallel_error_findings` produced by agents (not only rule-based path).

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section 14: Main tracer agent performs synthesis of findings and suggestions

**Single goal:** Move harness-change synthesis from rule-based middleware into the main tracer agent so the main agent synthesizes findings and suggestions (e.g. via a synthesis tool or a dedicated synthesis step), instead of `synthesize_harness_changes_from_findings` in middleware.

**Details:**
- Today: `TracerHarnessSynthesisMiddleware` (or equivalent) calls `synthesize_harness_changes_from_findings(state)` and injects `harness_change_set` / `harness_changes` into state; main agent only consumes them.
- Target: Main tracer agent performs synthesis. Options: (a) give the agent a tool that takes `parallel_error_findings` and returns a proposed `HarnessChangeSet` (agent calls tool, result written to state); (b) add a dedicated “synthesis” step in the graph where the model receives findings and outputs structured harness changes (e.g. via structured output or a tool). The graph result state still exposes `harness_change_set` and `harness_changes`.
- Reuse `HarnessChangeSet` and related schemas from `schemas/harness_changes.py`; do not change the API response shape. Remove or bypass the middleware that currently does rule-based synthesis so only the main agent produces the change set.

**Tech stack and dependencies**
- Libraries/packages: deep-agent library; existing `schemas.harness_changes`, `agents.tracer_state`, `agents.tracer_prompts` (add synthesis instructions if needed).
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/deep_agent_tracer.py | Add synthesis tool or synthesis step for main agent; ensure graph result state includes agent-produced harness_change_set; stop using rule-based synthesis middleware for this outcome. |
| src/backend/agents/tracer_prompts.py | Add synthesis instructions so the main agent knows when and how to produce harness change suggestions from findings. |
| src/backend/agents/harness_change_synthesis.py | Keep as reference or for fallback; or remove if fully replaced by agent-driven synthesis. |

**How to test:** Unit test: invoke deep-agent with state containing `parallel_error_findings`; assert result state includes `harness_change_set` produced by the model (tool call or structured output), not by `synthesize_harness_changes_from_findings`. Integration test: full tracer run; assert API response harness_change_set is present and produced by main agent path.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section 15: Aggregate feedback and human-in-the-loop for harness changes

**Single goal:** Add an explicit “aggregate feedback” step and an optional human-in-the-loop API so harness change suggestions can be reviewed or approved before being applied.

**Details:**
- Today: Output is a `HarnessChangeSet` (config/prompt/tool suggestions); no aggregation of feedback and no human approval step in the code.
- Target: (1) Define an aggregation step that combines agent-produced harness suggestions with optional external feedback (e.g. from a prior run or API). (2) Expose an API or flow (e.g. “proposed changes” endpoint + “approve/apply” or “reject”) so a human can review and approve or reject before changes are applied. (3) Apply harness changes only after approval (or when running in auto-apply mode); document the two modes.
- Do not change the shape of `HarnessChangeSet`; add only aggregation logic and the approval/apply flow.

**Tech stack and dependencies**
- Libraries/packages: None new beyond existing tracer and harness schemas.
- Tooling: None new.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/services/trace_analyzer_service.py | After graph returns, run aggregation (merge suggestions with any feedback); optionally enqueue or store “proposed changes” for approval. |
| src/backend/routers/tracer.py | Add or extend endpoints: e.g. GET/POST for proposed harness changes and approve/apply (or reject); or document that approval is out-of-band. |
| src/backend/schemas (or new) | Optional: feedback payload schema, approval result schema. |

**How to test:** Unit test: aggregation merges agent suggestions with feedback. API test: submit tracer run; fetch proposed changes; call approve (or reject); assert apply only occurs on approve. Manual: run with human-in-the-loop and confirm apply only after approval.

**Test results:** (Add when section is complete.)
- Command and outcome.

---
