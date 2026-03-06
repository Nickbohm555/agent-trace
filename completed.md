## Section 1: Add deep-agent library dependency

**Single goal:** Declare and lock the LangGraph deep-agent library so the tracer can be built with `create_deep_agent` (or equivalent) as the single graph implementation.

### Completed work
- Added `deepagents>=0.4.6` to backend dependencies in `src/backend/pyproject.toml`.
- Refreshed `src/backend/uv.lock` to include `deepagents` and its resolved transitive dependencies.
- No tracer implementation code changes were made in this section.

### Validation commands and outcomes
- `docker compose exec backend uv sync`
  - Outcome: success (`Resolved 93 packages ... Audited 90 packages`, no resolution errors).
- `docker compose exec backend uv run python -c "from deepagents import create_deep_agent; print('deepagents import ok (post-rebuild)')"`
  - Outcome: success (`deepagents import ok (post-rebuild)`).

### Container restart/rebuild logs
- Fresh start before work:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Dependency-change rebuild after updates:
  - `docker compose down`
  - `docker compose build`
  - `docker compose up -d`
  - `docker compose ps` showed `db`, `backend`, `frontend`, and `chrome` all `Up`.
- Post-rebuild service logs checked:
  - `docker compose logs --tail=120 backend` -> Uvicorn started, Alembic migration context loaded.
  - `docker compose logs --tail=120 frontend` -> Vite dev server ready.
  - `docker compose logs --tail=120 db` -> PostgreSQL ready to accept connections.

### Notes
- Build/runtime now includes `deepagents==0.4.6` in backend image.

## Section 2: Align tracer state with deep-agent state contract

**Single goal:** Ensure `TracerState` (or the state schema passed to the deep-agent) matches the library’s expected state shape and includes all keys the tracer needs so middleware and orchestration can rely on a single schema.

### Completed work
- Updated `src/backend/agents/tracer_state.py` so `TracerState.messages` is now a plain `list[AnyMessage]` contract (removed LangGraph-specific `add_messages` reducer annotation).
- Kept all tracer orchestration/middleware keys in `TracerState` (run and sandbox fields, reasoning fields, verification/time budget/loop detection fields, parallel analysis fields, and harness change fields).
- Added deep-agent tracer build logging in `src/backend/agents/deep_agent_tracer.py` to include `state_field_count` and `state_fields` for runtime visibility of the active schema.
- Expanded `tests/agents/test_deep_agent_tracer.py` to validate full tracer-state propagation and verify middleware uses `TracerState` as the registered deep-agent state schema.
- Added a type-contract test asserting the `TracerState.messages` annotation resolves to a plain list type.

### Validation commands and outcomes
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py`
  - Outcome: success (`9 passed in 2.14s`).

### Container restart/rebuild logs
- Fresh baseline restart before implementation:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Post-change runtime refresh:
  - `docker compose restart backend`
  - `docker compose ps` showed `db`, `backend`, `frontend`, and `chrome` all `Up`.
- Post-change logs checked:
  - `docker compose logs --no-color --tail=120 backend` -> Uvicorn startup complete; file-change reloads completed; service running.
  - `docker compose logs --no-color --tail=120 frontend` -> Vite dev server ready.
  - `docker compose logs --no-color --tail=120 db` -> PostgreSQL ready to accept connections.

### Notes
- Section 2 completed with state-schema alignment focused on deep-agent state contract while preserving existing tracer keys for upcoming middleware migrations.

## Section 3: Migrate reasoning budget to deep-agent

**Single goal:** Make reasoning compute (phase and level) configurable in the deep-agent path so planning/verification can use higher budget and implementation lower (reasoning sandwich).

### Completed work
- Added `TracerReasoningBudgetMiddleware` to `src/backend/agents/deep_agent_tracer.py`.
- The middleware now resolves effective reasoning phase and level per model turn using existing `tracer_config` utilities (`resolve_reasoning_phase`, `resolve_reasoning_level`, and default `TracerReasoningConfig` phase sandwich values).
- Added support for `reasoning_phase_levels` overrides from tracer state while preserving explicit `reasoning_level` as the highest-precedence override for the active turn.
- Wired middleware into `build_deep_agent_tracer(...)` so deep-agent model calls now receive reasoning settings through request model settings (`reasoning: {"effort": <level>}`).
- Added visibility logging for each deep-agent model call reasoning budget application (run_id, phase, level).
- Extended deep-agent tracer tests to assert reasoning budget propagation into model binding kwargs and resolved state values.

### Validation commands and outcomes
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py`
  - Outcome: success (`11 passed in 2.14s`).

### Container restart/rebuild logs
- Code-change refresh:
  - `docker compose restart backend`
- Runtime state check:
  - `docker compose ps` -> `db`, `backend`, `frontend`, and `chrome` all `Up` (db healthy).
- Post-change logs checked:
  - `docker compose logs --no-color --tail=120 backend frontend db`
  - Backend showed Uvicorn startup/reload cycles and application startup complete.
  - Frontend showed Vite dev server ready.
  - DB showed PostgreSQL ready to accept connections.

### Notes
- This section keeps deep-agent architecture intact and moves reasoning budget application directly into deep-agent model invocation path via middleware.

## Section 4: Migrate pre-completion verification to deep-agent middleware

**Single goal:** Before the tracer can finish, run a verification pass (remind agent to run tests and compare to spec) in the deep-agent path so the agent does not exit without testing.

### Completed work
- Added `TracerPreCompletionVerificationMiddleware` in `src/backend/agents/deep_agent_tracer.py`.
- Wired middleware into `build_deep_agent_tracer(...)` middleware registration so the deep-agent loop enforces verification before final completion.
- Middleware reuses existing helper logic from `src/backend/agents/tracer_middleware.py`:
  - `should_inject_pre_completion_checklist(...)`
  - `build_pre_completion_checklist_message(...)`
- Implemented the check in `after_model` with `@hook_config(can_jump_to=["model"])` and state updates:
  - appends a verification checklist `SystemMessage`,
  - sets `pre_completion_verified=True`,
  - sets `jump_to="model"` so one additional verification turn occurs.
- Added explicit middleware logging:
  - `"Injecting pre-completion verification checklist in deep-agent middleware"` with `run_id`.
- Updated/expanded `tests/agents/test_deep_agent_tracer.py`:
  - new test `test_build_deep_agent_tracer_injects_pre_completion_checklist_before_end`,
  - adjusted existing tests to set `pre_completion_verified=True` when they are not testing this middleware behavior.

### Validation commands and outcomes
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py`
  - Outcome: success (`12 passed in 2.30s`).

### Container restart/rebuild logs
- Pre-task full clean restart (fresh builds/logs):
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Post-change runtime refresh:
  - `docker compose restart backend`
  - `docker compose ps` -> `db`, `backend`, `frontend`, and `chrome` all `Up` (`db` healthy).
- Post-change logs reviewed:
  - `docker compose logs --no-color --tail=120 db backend frontend`
  - Backend: Alembic context loaded, Uvicorn reloader/server startup complete, file-change reloads completed, service running.
  - Frontend: Vite dev server ready.
  - DB: PostgreSQL ready to accept connections.

### Notes
- Section 4 is complete and keeps deep-agent architecture intact while reusing existing checklist helper logic.

## Section 5: Migrate time-budget injection to deep-agent middleware

**Single goal:** Inject time-remaining or step-remaining warnings into the tracer’s context in the deep-agent path so the agent shifts to verification and submission under limits.

### Completed work
- Added `TracerTimeBudgetMiddleware` in `src/backend/agents/deep_agent_tracer.py`.
- Wired the middleware into `build_deep_agent_tracer(...)` so it runs for each model turn.
- Middleware reuses existing time-budget helpers from `src/backend/agents/tracer_middleware.py` via `apply_time_budget_injection(...)`.
- Middleware now updates deep-agent state for:
  - `run_started_at_epoch_seconds`
  - `agent_step_count`
  - `time_budget_last_notice_step` (when notice emitted)
- Middleware appends a time-budget `SystemMessage` when helper conditions are met.
- Added test `test_build_deep_agent_tracer_injects_time_budget_warning_and_updates_step_count` in `tests/agents/test_deep_agent_tracer.py`.
- Fixed deep-agent message-state compatibility discovered in fresh rebuild:
  - Restored `TracerState.messages` to `Annotated[list[AnyMessage], add_messages]` so deep-agent middleware receives iterable message lists instead of `Overwrite(...)` wrappers.
  - Updated state-contract test to assert list contract with reducer metadata and updated propagation test expectations for incremented step count.

### Validation commands and outcomes
- `docker compose exec backend uv run pytest src/backend/tests/agents/test_deep_agent_tracer.py`
  - Outcome: failed (incorrect path in container; file not found).
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py`
  - Outcome: initially failed (`10 failed, 3 passed`) due `Overwrite` message-wrapper runtime errors; fixed in this section.
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py`
  - Outcome: success (`13 passed in 2.76s`).

### Container restart/rebuild logs
- Pre-task full clean restart (fresh builds/logs):
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
  - `docker compose ps` -> `db`, `backend`, `frontend`, and `chrome` all `Up` (`db` healthy).
- Post-change runtime refresh:
  - `docker compose restart backend`
- Post-change logs reviewed:
  - `docker compose logs --no-color --tail=200 backend frontend db`
  - Backend: Alembic migration context loaded; Uvicorn startup complete; watch reloads after edited files; final server process running.
  - Frontend: Vite dev server ready.
  - DB: PostgreSQL ready to accept connections.

### Notes
- Section 5 is complete and keeps deep-agent architecture intact by reusing existing time-budget helper logic via middleware.
- The fresh-rebuild compatibility fix for `TracerState.messages` was necessary to keep deep-agent built-in summarization middleware stable.

## Section 6: Migrate loop-detection to deep-agent middleware

**Single goal:** Track per-file edit counts and, after N edits to the same file, inject a “reconsider your approach” nudge in the deep-agent path to avoid doom loops.

### Completed work
- Added `TracerLoopDetectionMiddleware` to `src/backend/agents/deep_agent_tracer.py`.
- Wired the middleware into `build_deep_agent_tracer(...)` middleware registration.
- Middleware now inspects the most recent model `AIMessage` tool calls and reuses `apply_loop_detection_injection(...)` from `src/backend/agents/tracer_middleware.py`.
- Middleware updates deep-agent state keys:
  - `edit_file_counts`
  - `loop_detection_nudged_files`
- When threshold is reached, middleware appends the generated loop-detection `SystemMessage` and logs an info event with `run_id` and nudged files.
- Added unit test `test_build_deep_agent_tracer_injects_loop_detection_notice_for_repeated_edits` in `src/backend/tests/agents/test_deep_agent_tracer.py` to trigger repeated `edit_file` calls and assert nudge injection/state updates.

### Validation commands and outcomes
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py`
  - Outcome: success (`14 passed in 3.27s`).

### Container restart/rebuild logs
- Pre-task full clean restart (fresh builds/logs):
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Post-change runtime refresh:
  - `docker compose restart backend`
  - `docker compose ps` -> `db`, `backend`, `frontend`, and `chrome` all `Up` (`db` healthy).
- Post-change logs reviewed:
  - `docker compose logs --tail=120 backend` -> Alembic context + Uvicorn startup complete, reload after file changes, final server process running.
  - `docker compose logs --tail=120 frontend` -> Vite dev server ready.
  - `docker compose logs --tail=120 db` -> PostgreSQL ready to accept connections.

### Notes
- Section 6 is complete and reuses existing loop-detection helper logic without changing tool contracts or API shape.

## Section 7: Migrate parallel error analysis to deep-agent flow

**Single goal:** Run parallel error-analysis workers and inject their findings into deep-agent state so the main agent can use them (Trace Analyzer Skill pattern).

**Details:**
- Load traces by run_id (or trace_ids) via TraceStorageService; run existing `analyze_errors_in_parallel` (error_analysis_agent); inject parallel_error_findings and parallel_error_count into state before or at the start of deep-agent execution.
- Can be done in orchestration (before invoking the graph) or in a deep-agent middleware that runs once when run_id is set and parallel_analysis_completed is false; set parallel_analysis_completed when done.
- No change to HarnessChangeSet schema or synthesis logic in this section; only injection of findings.

### Completed work
- Added `TracerParallelErrorAnalysisMiddleware` in `src/backend/agents/deep_agent_tracer.py`.
- Middleware reuses existing logic from `src/backend/agents/error_analysis_agent.py` (`collect_error_tasks`, `analyze_errors_in_parallel`) and trace loading via `TraceStorageService` + `TraceStorageQuery`.
- Middleware behavior:
  - runs once per run when `parallel_analysis_completed` is not set,
  - skips when `run_id` is missing,
  - loads traces by `run_id`, computes error tasks, runs parallel analysis, and injects:
    - `parallel_error_findings`
    - `parallel_error_count`
    - `parallel_analysis_completed=True`
- Registered middleware in `build_deep_agent_tracer(...)` so findings are injected in deep-agent flow before model turns.
- Added integration-style test `test_build_deep_agent_tracer_injects_parallel_error_findings_from_trace_storage` in `src/backend/tests/agents/test_deep_agent_tracer.py`:
  - persists a failing trace to storage,
  - invokes deep-agent graph with `run_id`,
  - asserts injected state keys and expected fix-category payload.

### Validation commands and outcomes
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py`
  - Outcome: success (`15 passed in 2.96s`).

### Container restart/rebuild logs
- Pre-task full clean restart (fresh builds/logs):
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Post-change runtime refresh:
  - `docker compose restart backend`
- Running state check:
  - `docker compose ps` -> `db`, `backend`, `frontend`, and `chrome` all `Up` (`db` healthy).
- Logs reviewed:
  - `docker compose logs --tail=120 backend` -> Alembic context loaded; Uvicorn startup complete; reloads observed for edited files; final server process running.
  - `docker compose logs --tail=80 frontend` -> Vite dev server ready.
  - `docker compose logs --tail=80 db` -> PostgreSQL ready to accept connections.

### Notes
- Section 7 completed in deep-agent middleware without changing harness synthesis schema/logic.

## Section 8: Migrate harness change synthesis to deep-agent output

**Single goal:** Produce structured HarnessChangeSet from parallel_error_findings in the deep-agent path so the tracer returns harness change suggestions.

**Details:**
- After parallel findings are available, convert them to HarnessChangeSet using existing logic (e.g. _synthesize_harness_changes from langgraph_agent or equivalent); emit harness_change_set and harness_changes in graph result state.
- Can be implemented as a post-agent middleware, a final step in the graph, or in orchestration after graph returns by reading state; choose one and document.
- No change to HarnessChangeSet schema; reuse schemas/harness_changes.py.

### Completed work
- Added shared harness synthesis module: `src/backend/agents/harness_change_synthesis.py` with `synthesize_harness_changes_from_findings(...)`.
- Migrated deep-agent path to synthesize harness changes via new `TracerHarnessSynthesisMiddleware` in `src/backend/agents/deep_agent_tracer.py`.
- Middleware now injects both:
  - `harness_change_set`
  - `harness_changes`
  when parallel findings are present and no existing change set is already in state.
- Added runtime visibility logging for deep-agent harness synthesis injection (run_id, change_count, trace_id_count).
- Updated legacy LangGraph implementation to reuse the same shared synthesis helper from `langgraph_agent.py`, removing duplicate synthesis logic.
- Added deep-agent tests:
  - `test_build_deep_agent_tracer_synthesizes_harness_change_set_from_findings`
  - `test_build_deep_agent_tracer_skips_harness_change_synthesis_without_findings`

### Validation commands and outcomes
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py`
  - Outcome: success (`17 passed in 3.55s`).
- `docker compose exec backend uv run pytest tests/agents/test_langgraph_agent.py`
  - Outcome: success (`14 passed in 1.27s`).
- `curl -s -o /tmp/backend_docs.html -w '%{http_code}\\n' http://localhost:8001/docs`
  - Outcome: success (`200`).

### Container restart/rebuild logs
- Pre-task full clean restart (fresh builds/logs):
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Post-change runtime refresh:
  - `docker compose restart backend`
- Running state check:
  - `docker compose ps` -> `db`, `backend`, `frontend`, and `chrome` all `Up` (`db` healthy).
- Logs reviewed:
  - `docker compose logs --tail=160 backend` -> Alembic + Uvicorn startup/reload completed; app startup complete.
  - `docker compose logs --tail=80 frontend` -> Vite dev server ready.
  - `docker compose logs --tail=120 db` -> PostgreSQL ready to accept connections.

### Notes
- Section 8 completed using middleware in deep-agent execution flow (not orchestration post-processing), preserving existing `HarnessChangeSet` schema.

## Section 9: Switch orchestration to deep-agent graph

**Single goal:** TraceAnalyzerService uses build_deep_agent_tracer as the graph builder and invokes it with the same request contract (run_id, sandbox_path, etc.); no code path may call build_tracer_graph for the main tracer.

**Details:**
- Set graph_builder to build_deep_agent_tracer (or a thin wrapper that passes services and returns the same invoke contract).
- _invoke_tracer_graph must pass initial state (run_id, sandbox_path, max_runtime_seconds, max_steps, etc.) and parse result state (harness_change_set) from the deep-agent graph return value.
- Preserve TraceAnalyzerRequest / TraceAnalyzerResult and evaluation (baseline/post-change) flow; only the graph implementation changes.

### Completed work
- Switched `TraceAnalyzerService` default graph builder from `build_tracer_graph` to `build_deep_agent_tracer` in `src/backend/services/trace_analyzer_service.py`.
- Kept request/response contract unchanged (`TraceAnalyzerRequest`, `TraceAnalyzerResult`, baseline/post-change evaluation flow).
- Updated `_invoke_tracer_graph` to pass deep-agent initial state keys:
  - `messages`
  - `run_id`
  - `sandbox_path`
  - `pre_completion_verified`
  - optional `max_runtime_seconds`
  - optional `max_steps`
- Added deep-agent invocation/result logs for run visibility (`Invoking tracer graph with deep-agent state`, `Received tracer graph result state`).
- Added graph-result normalization helper (`_coerce_graph_result_to_state`) to robustly parse deep-agent return values.
- Fixed runtime deep-agent compatibility issues discovered during live POST testing:
  - `TracerReasoningBudgetMiddleware` now skips injecting `reasoning` model settings for Anthropic model classes (prevents `Messages.create() got an unexpected keyword argument 'reasoning'`).
  - Added regression test: `test_reasoning_budget_middleware_skips_reasoning_settings_for_anthropic_models`.
- Added orchestration fallback for missing model credentials during deep-agent invoke:
  - catches auth-resolution `TypeError`, logs warning, and returns empty graph state so API returns a valid empty `harness_change_set` rather than `500`.

### Validation commands and outcomes
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py`
  - Outcome: success (`18 passed in 3.54s`).
- `docker compose exec backend uv run pytest tests/services/test_trace_analyzer_service.py tests/api/test_tracer_run.py`
  - Outcome: success (`5 passed in 1.59s`).
- Live endpoint check:
  - `curl -X POST http://localhost:8001/api/tracer/run -d '{"run_id":"run-section9-smoke","limit":1,"max_runtime_seconds":30,"max_steps":1}'`
  - Initial outcome: `500` (fixed in this section).
  - Final outcome after fixes: `200`.
  - Final response contained `harness_change_set`:
    - `summary="No harness changes were synthesized by the tracer graph."`

### Container restart/rebuild logs
- Pre-task full clean restart (fresh builds/logs):
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Post-change refreshes:
  - `docker compose restart backend`
- Running state check:
  - `docker compose ps` -> `db`, `backend`, `frontend`, `chrome` all `Up` (`db` healthy).
- Logs reviewed:
  - `docker compose logs --tail=180 backend`
    - showed initial POST `500` with Anthropic `reasoning` error,
    - showed initial missing credentials error,
    - showed final warning fallback (`Tracer deep-agent model credentials are missing; continuing with empty graph result`) and `POST /api/tracer/run ... 200 OK`.
  - `docker compose logs --tail=80 frontend` -> Vite dev server ready.
  - `docker compose logs --tail=80 db` -> PostgreSQL ready to accept connections.

### Notes
- Main tracer orchestration now points to deep-agent by default.
- In environments without model credentials, tracer run now degrades gracefully to an empty synthesized change set instead of failing the API request.
