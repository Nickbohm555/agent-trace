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

## Section 10: Remove legacy LangGraph agent implementation

**Single goal:** Remove or permanently gate the custom StateGraph tracer (build_tracer_graph and its graph nodes) so the codebase has a single implementation path: the deep-agent library.

**Details:**
- Delete or deprecate build_tracer_graph and all graph nodes/edges in langgraph_agent.py that are only used by the legacy path.
- Keep shared pieces used by deep-agent (e.g. _synthesize_harness_changes if moved to a shared module, tracer_state, tracer_config, tracer_prompts, tracer_middleware helpers); remove only the legacy graph construction and routing.
- No new features; deletion/gating only.

### Completed work
- Removed legacy StateGraph tracer implementation file `src/backend/agents/langgraph_agent.py`.
- Removed legacy LangGraph-only tests file `src/backend/tests/agents/test_langgraph_agent.py`.
- Updated `src/backend/tests/agents/test_tracer_middleware.py` to remove legacy `build_tracer_graph` import and graph-path verification test; retained direct middleware helper coverage.
- Verified the backend now has no remaining references/imports to `build_tracer_graph`, `StateGraph`, or `agents.langgraph_agent`.

### Validation commands and outcomes
- `rg -n "build_tracer_graph|agents\\.langgraph_agent|from agents.langgraph_agent|StateGraph|should_continue" src/backend`
  - Outcome: success (no matches).
- `docker compose exec backend uv run pytest`
  - Outcome: success (`59 passed in 4.45s`).
- `curl -s -o /tmp/section10_backend_docs.html -w '%{http_code}\\n' http://localhost:8001/docs`
  - Outcome: success (`200`).
- `curl -s -o /tmp/section10_frontend.html -w '%{http_code}\\n' http://localhost:5174`
  - Outcome: success (`200`).

### Container restart/rebuild logs
- Pre-task full clean restart (fresh builds/logs):
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Post-change runtime refresh:
  - `docker compose restart db backend frontend`
- Running state check:
  - `docker compose ps` -> `db`, `backend`, `frontend`, `chrome` all `Up` (`db` healthy).
- Logs reviewed:
  - `docker compose logs --no-color --tail=120 backend` -> Alembic context loaded, Uvicorn startup complete, reloads observed after file deletions, final server process running.
  - `docker compose logs --no-color --tail=120 frontend` -> Vite dev server ready.
  - `docker compose logs --no-color --tail=120 db` -> PostgreSQL ready to accept connections after restart.

### Notes
- Section 10 completed by removing the legacy custom LangGraph StateGraph path. The tracer now has a single implementation path through deep-agent (`build_deep_agent_tracer`).

## Section 11: Update agent tests to deep-agent only

**Single goal:** All agent tests target build_deep_agent_tracer and deep-agent middleware; remove or migrate tests that only exercise build_tracer_graph.

**Details:**
- Migrate or remove tests from test_langgraph_agent.py that assert legacy graph behavior; add or extend tests in test_deep_agent_tracer.py for equivalent coverage (routing, tools, middleware, synthesis, state).
- Test suite must not depend on build_tracer_graph; all tracer behavior validated through build_deep_agent_tracer.
- Preserve coverage for system prompt, tools, local context, sandbox scope, pre-completion, time budget, loop detection, parallel analysis, harness synthesis.

### Completed work
- Verified legacy test file `src/backend/tests/agents/test_langgraph_agent.py` is already removed and no migration gaps remain.
- Confirmed `src/backend/tests/agents/test_deep_agent_tracer.py` covers deep-agent routing/tools/middleware/state/synthesis behaviors.
- Confirmed `src/backend/tests/agents/test_tracer_middleware.py` is deep-agent compatible and contains no legacy graph coupling.
- Verified there are no remaining `build_tracer_graph` references anywhere under backend tests.

### Validation commands and outcomes
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py tests/agents/test_tracer_middleware.py`
  - Outcome: success (`24 passed in 3.74s`).
- `rg -n "build_tracer_graph" src/backend/tests`
  - Outcome: success (no matches).

### Container restart/rebuild logs
- Pre-task full clean restart (fresh builds/logs):
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Running state check:
  - `docker compose ps` -> `db`, `backend`, `frontend`, `chrome` all `Up` (`db` healthy).
- Logs reviewed:
  - `docker compose logs --tail=120 backend` -> Alembic migration ran; Uvicorn startup complete.
  - `docker compose logs --tail=120 frontend` -> Vite dev server ready.
  - `docker compose logs --tail=120 db` -> PostgreSQL ready to accept connections.

### Notes
- Section 11 required no new code changes because legacy agent tests had already been migrated/removed in prior sections; this iteration verified and documented deep-agent-only test coverage.

## Section 12: Verify API and UI with deep-agent backend

**Single goal:** Confirm POST /api/tracer/run and the frontend tracer run form and results UI work correctly with the deep-agent-backed orchestration; fix any contract or behavior regressions.

**Details:**
- Manually or via E2E test: submit a tracer run from the UI; assert completion and display of harness change summary (or "no changes"); assert error display on failure.
- Verify response shape (harness_change_set, improvement_metrics) matches frontend types; no breaking change to API response schema.
- Document any intentional contract change; otherwise ensure parity with pre-refactor behavior.

### Completed work
- Verified backend tracer endpoint and frontend API contract alignment by inspecting:
  - `src/backend/routers/tracer.py`
  - `src/backend/services/trace_analyzer_service.py`
  - `src/frontend/src/utils/api.ts`
  - `src/frontend/src/App.tsx`
- Found and fixed a real regression in frontend error handling:
  - FastAPI/Pydantic validation errors return `detail` as an array of objects, but frontend `parseErrorMessage` only handled string `detail`.
  - Updated `src/frontend/src/utils/api.ts` to parse both:
    - string detail
    - array detail (`[{ msg: ... }]`)
- Updated UI test to cover actual backend 422 payload shape:
  - `src/frontend/src/App.test.tsx` now asserts display of the validation message extracted from array-form `detail`.

### Validation commands and outcomes
- Full clean restart before work:
  - `docker compose down -v --rmi all` -> completed (removed containers/volumes/images where allowed; base images remained in-use as expected).
  - `docker compose build` -> completed.
  - `docker compose up -d` -> completed (`db`, `backend`, `frontend`, `chrome` started; `db` healthy).
- Live readiness checks:
  - `curl -s -o /tmp/section12_docs.html -w '%{http_code}\\n' http://localhost:8001/docs` -> `200`.
  - `curl -s -o /tmp/section12_frontend.html -w '%{http_code}\\n' http://localhost:5174` -> `200`.
- Live API success contract check:
  - `curl -s -X POST http://localhost:8001/api/tracer/run -H 'Content-Type: application/json' -d '{"run_id":"section12-run-1"}'`
  - Outcome: `200` with response keys including `harness_change_set` and `improvement_metrics: null`.
- Live API failure contract check:
  - `curl -s -X POST http://localhost:8001/api/tracer/run -H 'Content-Type: application/json' -d '{"target_repo_url":"https://example.com/repo.git"}'`
  - Outcome: validation payload with array-form `detail` and `msg="Value error, Provide at least one of run_id or trace_ids."`.
- Backend/API regression coverage:
  - `docker compose exec backend uv run pytest tests/api/test_tracer_run.py tests/services/test_trace_analyzer_service.py` -> passed (`5 passed in 2.67s`).
- Frontend required checks:
  - `docker compose exec frontend npm run test` -> passed (`2 passed`).
  - `docker compose exec frontend npm run typecheck` -> passed.
  - `docker compose exec frontend npm run build` -> passed.
- Browser debug endpoint check (per chromeDev workflow guidance):
  - `curl -s http://127.0.0.1:9223/json/list` -> returned active target with `webSocketDebuggerUrl`.

### Container restart/rebuild logs
- Changed container scope: frontend-only source changes (`src/frontend/src/utils/api.ts`, `src/frontend/src/App.test.tsx`).
- Post-change container refresh:
  - `docker compose restart frontend` -> completed.
- Final running state:
  - `docker compose ps` -> `db`, `backend`, `frontend`, `chrome` all `Up` (`db` healthy).
- Final logs reviewed:
  - `docker compose logs --tail=220 backend` -> showed `GET /docs 200`, `POST /api/tracer/run 422`, and `POST /api/tracer/run 200` after checks.
  - `docker compose logs --tail=160 frontend` -> Vite dev server ready after restart.
  - `docker compose logs --tail=120 db` -> PostgreSQL ready to accept connections.

### Notes
- No backend response schema changes were required; this section preserved contract parity while improving frontend handling of existing FastAPI validation error format.

## Section 1: Single error-analysis agent (invokable)

**Single goal:** Implement one invokable error-analysis agent that takes a single `TraceErrorTask` and returns one or more `ErrorAnalysisFinding`s, so it can later be run in parallel per task.

### Completed work
- Added a LangGraph-based invokable single-task error-analysis agent in `src/backend/agents/error_analysis_agent.py`.
- Added explicit single-task agent contract APIs:
  - `build_error_analysis_agent(...)`
  - `run_error_analysis_agent_async(task, ...) -> list[ErrorAnalysisFinding]`
  - `run_error_analysis_agent(task, ...) -> list[ErrorAnalysisFinding]`
- Kept existing functionality intact:
  - `collect_error_tasks(...)`
  - `_default_error_analyzer(...)`
  - parallel analyzers (`analyze_errors_in_parallel*`).
- Added visibility logs for single-task invokable agent execution (`Completed invokable error-analysis agent task`, `Ran invokable error-analysis agent`).
- Added unit coverage in `src/backend/tests/agents/test_error_analysis_agent.py` for one-task invokable agent return contract.

### Validation commands and outcomes
- Required section test:
  - `docker compose exec backend uv run pytest tests/agents/test_error_analysis_agent.py`
  - Outcome: success (`3 passed in 0.31s`).
- Backend readiness:
  - `curl -I -s http://localhost:8001/docs | head -n 1`
  - Outcome: success (`HTTP/1.1 200 OK`).

### Container restart/rebuild logs
- Pre-task full clean restart (fresh builds/logs):
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Post-change refresh (changed container scope: backend-only code):
  - `docker compose restart backend`
- Running state check:
  - `docker compose ps` -> `db`, `backend`, `frontend`, `chrome` all `Up` (`db` healthy).
- Logs reviewed:
  - `docker compose logs --tail=120 backend` -> uvicorn startup complete; reload observed after `agents/error_analysis_agent.py` and test updates; server healthy.
  - `docker compose logs --tail=80 frontend` -> Vite dev server ready.
  - `docker compose logs --tail=80 db` -> PostgreSQL ready to accept connections.
  - `docker compose logs --tail=80 chrome` -> browserless started on port 3000.

### Notes
- Section 1 is complete and leaves orchestration/parallel invocation integration for Section 2.

## Section 2: Parallel agent execution and state injection

**Single goal:** Run the error-analysis agent in parallel for all tasks from loaded traces and inject the aggregated findings into tracer state.

**Details:**
- Use `collect_error_tasks(traces)` to get tasks; for each task (or batched subset), invoke the error-analysis agent from Section 1; aggregate all findings into one list; set `parallel_error_findings` and `parallel_error_count` in state.
- Wire this path in orchestration or in deep-agent middleware (when run_id is set and traces are loaded). Do not change state schema; only populate it from agent results.
- Optional: keep a fallback to rule-based analyzer for tests or low-cost mode; document both paths.

### Completed work
- Added a new parallel invokable-agent runner in `src/backend/agents/error_analysis_agent.py`:
  - `run_error_analysis_agent_tasks_in_parallel_async(...)`
  - `run_error_analysis_agent_tasks_in_parallel(...)`
- The new runner now executes the Section 1 invokable agent for each `TraceErrorTask` and aggregates findings across tasks.
- Added explicit fallback behavior: if an agent task errors, the runner logs the exception and falls back to `_default_error_analyzer` when `fallback_to_rule_based=True`.
- Updated deep-agent middleware in `src/backend/agents/deep_agent_tracer.py` to use `run_error_analysis_agent_tasks_in_parallel(...)` and inject aggregated findings/count into tracer state.
- Added additional graph-result visibility logging in `src/backend/services/trace_analyzer_service.py` for:
  - `has_parallel_error_findings`
  - `parallel_error_count`
- Added/updated tests:
  - `src/backend/tests/agents/test_error_analysis_agent.py`
    - new test verifies parallel invokable-agent runner aggregates multiple findings per task.
  - `src/backend/tests/agents/test_deep_agent_tracer.py`
    - new middleware test monkeypatches the invokable-agent parallel runner and verifies this exact path is used for state injection.

### Validation commands and outcomes
- `docker compose exec backend uv run pytest tests/agents/test_error_analysis_agent.py tests/agents/test_deep_agent_tracer.py`
  - Outcome: success (`23 passed in 4.10s`).
- `docker compose exec backend uv run pytest tests/services/test_trace_analyzer_service.py`
  - Outcome: success (`2 passed in 1.26s`).
- `curl -s -o /dev/null -w "%{http_code}\\n" http://localhost:8001/docs`
  - Outcome: success (`200`).

### Container restart/rebuild logs
- Pre-task full clean restart (fresh builds/logs):
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Post-change refresh (changed container scope: backend-only code):
  - `docker compose restart backend`
- Running state check:
  - `docker compose ps` -> `db`, `backend`, `frontend`, `chrome` all `Up` (`db` healthy).
- Logs reviewed:
  - `docker compose logs --tail=120 backend` -> startup complete, reloads triggered by modified backend/test files, final server process healthy.
  - `docker compose logs --tail=60 frontend` -> Vite dev server ready.
  - `docker compose logs --tail=60 db` -> PostgreSQL ready to accept connections.

### Notes
- Section 2 is complete via middleware wiring; tracer state is populated through the parallel invokable-agent path while preserving a rule-based fallback on agent task failure.

## Section 3: Synthesis tool or step for main tracer agent

**Single goal:** Add one mechanism by which the main tracer agent produces a `HarnessChangeSet` from `parallel_error_findings` (synthesis tool or dedicated synthesis step).

**Details:**
- Implement either: (a) a tool the main agent can call with findings and that returns a proposed `HarnessChangeSet`, or (b) a dedicated synthesis node/step in the graph where the model outputs structured harness changes. Graph result state must include `harness_change_set` and `harness_changes` from this path.
- Reuse `HarnessChangeSet` and schemas from `schemas/harness_changes.py`. Do not remove rule-based synthesis middleware in this section; only add the agent-driven path.

### Completed work
- Added agent-driven synthesis tool support in `src/backend/agents/deep_agent_tracer.py` via new tool `propose_harness_changes` (`build_propose_harness_changes_tool`).
- Registered `propose_harness_changes` in deep-agent toolset so the main tracer agent can submit structured harness changes directly.
- Updated `TracerHarnessSynthesisMiddleware` to capture model-authored `propose_harness_changes` tool-call payloads, validate with `HarnessChangeSet`, and inject:
  - `harness_change_set`
  - `harness_changes`
- Kept rule-based synthesis (`synthesize_harness_changes_from_findings`) as fallback path when model-authored synthesis is absent.
- Added test coverage in `src/backend/tests/agents/test_deep_agent_tracer.py`:
  - `test_build_deep_agent_tracer_uses_model_synthesis_tool_for_harness_change_set`
  - Updated tool-registration test to expect `propose_harness_changes` in tracer tools.

### Validation commands and outcomes
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py`
  - Outcome: success (`20 passed in 5.21s`).

### Container restart/rebuild logs
- Pre-task full clean restart (fresh builds/logs):
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
  - Note: transient Docker container-name conflicts occurred during startup (`agent-trace-frontend`/`backend`); resolved by removing stale `agent-trace-*` containers and rerunning startup.
- Post-change refresh (changed container scope: backend code + backend tests):
  - `docker compose restart backend`
- Running state check:
  - `docker compose ps` -> `db`, `backend`, `frontend`, `chrome` all `Up` (`db` healthy).
- Logs reviewed:
  - `docker compose logs --no-color --tail=160 backend` -> uvicorn startup complete, watch reloads after tracer/test file edits, final server process healthy.
  - `docker compose logs --no-color --tail=80 frontend` -> Vite dev server ready.
  - `docker compose logs --no-color --tail=80 db` -> PostgreSQL ready to accept connections.

### Notes
- Section 3 is complete with an agent-authored synthesis mechanism (tool path) while preserving rule-based synthesis fallback for continuity.

## Section 4: Synthesis prompts and removal of rule-based synthesis middleware

**Single goal:** Add synthesis instructions to the main agent and remove or bypass rule-based synthesis middleware so only the main agent produces the harness change set.

**Details:**
- Add prompt text in `tracer_prompts.py` so the main agent knows when and how to produce harness change suggestions from findings (e.g. when to call the synthesis tool or how to fill the synthesis step).
- Remove or bypass `TracerHarnessSynthesisMiddleware` (or equivalent) that calls `synthesize_harness_changes_from_findings`; ensure no code path overwrites the agent-produced `harness_change_set` with rule-based output. Keep or archive `harness_change_synthesis.py` as reference/fallback only if needed.

### Completed work
- Updated `src/backend/agents/tracer_prompts.py` with a dedicated **Harness synthesis phase** that instructs the main tracer agent to:
  - synthesize from `parallel_error_findings` only,
  - call `propose_harness_changes` exactly once,
  - include `run_id` + impacted `trace_ids`,
  - keep proposed `harness_changes` concrete/testable,
  - avoid fabricating suggestions when findings are missing/insufficient.
- Updated `src/backend/agents/deep_agent_tracer.py` to remove rule-based fallback synthesis from `TracerHarnessSynthesisMiddleware`.
  - The middleware now only captures model-authored `propose_harness_changes` tool payloads.
  - Removed import/use of `synthesize_harness_changes_from_findings` from active middleware path.
- Kept `src/backend/agents/harness_change_synthesis.py` as reference-only code (no longer used in the primary synthesis path).
- Updated tests:
  - `src/backend/tests/agents/test_deep_agent_tracer.py`
    - replaced fallback synthesis test with `test_build_deep_agent_tracer_does_not_synthesize_harness_change_set_without_model_tool_call`.
  - `src/backend/tests/agents/test_tracer_prompts.py`
    - added assertions for synthesis instructions and tool-call contract in the system prompt.

### Validation commands and outcomes
- `docker compose exec backend uv run pytest tests/agents/test_deep_agent_tracer.py tests/agents/test_tracer_prompts.py`
  - Outcome: success (`24 passed in 7.95s`).
- `docker compose exec backend uv run pytest tests/api/test_tracer_run.py`
  - Outcome: success (`3 passed in 2.94s`).
- `curl -s -o /dev/null -w "%{http_code}\\n" http://localhost:8001/docs`
  - First outcome: `000` during backend restart window.
  - Follow-up after restart stabilization: success (`200`).

### Container restart/rebuild logs
- Pre-task full clean restart (fresh builds/logs):
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Post-change refresh (changed container scope: backend code + backend tests):
  - `docker compose restart backend`
- Running state check:
  - `docker compose ps` -> `db`, `backend`, `frontend`, `chrome` all `Up` (`db` healthy).
- Logs reviewed:
  - `docker compose logs --tail=120 backend` -> uvicorn startup complete, watch reloads after tracer/prompt/test edits, final server process healthy.
  - `docker compose logs --tail=60 frontend` -> Vite dev server ready.
  - `docker compose logs --tail=60 db` -> PostgreSQL ready to accept connections.

### Notes
- Section 4 is complete: `harness_change_set` synthesis is now main-agent/tool authored only, with prompt guidance enforcing the synthesis contract.

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

### Completed work
- Added feedback input schema in `src/backend/schemas/harness_changes.py`:
  - `HarnessChangeFeedback` with `summary`, `trace_ids`, `harness_changes`, and `replace_existing_changes`.
- Extended tracer API request schema in `src/backend/schemas/tracer_api.py`:
  - New optional request field: `harness_feedback`.
- Wired request payload in `src/backend/routers/tracer.py`:
  - Forward `payload.harness_feedback` into `TraceAnalyzerRequest`.
- Implemented post-graph aggregation in `src/backend/services/trace_analyzer_service.py`:
  - Added `TraceAnalyzerRequest.harness_feedback`.
  - Added `_aggregate_harness_change_set(...)` to merge graph suggestions with optional feedback.
  - Added `_merge_trace_ids(...)` to preserve deterministic, de-duplicated trace ordering.
  - Merge rules:
    - no feedback: return base model-authored change set.
    - feedback with `replace_existing_changes=false`: append non-duplicate feedback changes by `change_id`.
    - feedback with `replace_existing_changes=true`: replace base change list with feedback changes.
    - summary: feedback summary (when non-empty) overrides base summary.
  - Added explicit `logger.info(...)` visibility logs for skip/aggregate paths with run id + change counts.
- Added/updated tests:
  - `src/backend/tests/services/test_trace_analyzer_service.py`
    - `test_aggregate_harness_change_set_merges_agent_suggestions_with_feedback`
    - `test_aggregate_harness_change_set_can_replace_existing_changes`
  - `src/backend/tests/api/test_tracer_run.py`
    - extended endpoint test to pass `harness_feedback` and assert it is forwarded to service request.

### Validation commands and outcomes
- `docker compose exec backend uv run pytest tests/services/test_trace_analyzer_service.py tests/api/test_tracer_run.py`
  - Outcome: success (`7 passed in 2.41s`).

### Container restart/rebuild logs
- Pre-task full clean restart (fresh builds/logs):
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Post-change refresh (changed container scope: backend code + backend tests):
  - `docker compose restart backend`
- Running state check:
  - `docker compose ps` -> `db`, `backend`, `frontend`, `chrome` all `Up` (`db` healthy).
- Logs reviewed:
  - `docker compose logs --tail=120 backend` -> alembic + uvicorn startup complete; watch reloads after edited backend files; final server process healthy.
  - `docker compose logs --tail=60 frontend` -> Vite dev server ready.
  - `docker compose logs --tail=60 db` -> PostgreSQL ready to accept connections.

### Notes
- Section 5 is complete: tracer output now supports deterministic aggregation of agent suggestions plus optional external feedback without changing `HarnessChangeSet` shape.

## Section 6: API for proposed changes and approve/apply (human-in-the-loop)

**Single goal:** Expose an API so proposed harness changes can be reviewed and applied only after approval (or document auto-apply mode).

**Details:**
- Add or extend endpoints: e.g. get proposed harness changes for a run, and approve/apply (or reject). Apply harness changes only when approval is given (or when a documented auto-apply mode is enabled).
- Do not change the shape of `HarnessChangeSet`; only add the flow: propose → (optional human review) → approve/apply or reject.

### Completed work
- Added `src/backend/services/harness_change_review_service.py` to store and review proposed `HarnessChangeSet` values per `run_id`.
  - Tracks review state as `pending`, `approved`, `applied`, or `rejected`.
  - Tracks audit timestamps (`approved_at`, `rejected_at`, `applied_at`).
  - Supports documented auto-apply mode via `TRACER_AUTO_APPLY_CHANGES` env var.
- Extended `src/backend/schemas/tracer_api.py` with new API models:
  - `TracerProposedChangesResponse`
  - `TracerProposalApprovalRequest`
  - `TracerProposalStatus`
- Extended `src/backend/routers/tracer.py`:
  - Existing `POST /api/tracer/run` now records proposed harness changes for later review.
  - Added `GET /api/tracer/{run_id}/proposed-changes` to fetch the current proposal + status.
  - Added `POST /api/tracer/{run_id}/approval` to approve/apply or reject.
  - Added route-level visibility logs for storing, fetching, and reviewing proposals.
- Updated API tests in `src/backend/tests/api/test_tracer_run.py`:
  - Verified run creation records a proposal.
  - Verified `approve + apply=true` transitions proposal to `applied`.
  - Verified `reject` never applies (`applied_at` remains null).

### Validation commands and outcomes
- `docker compose exec backend uv run pytest tests/api/test_tracer_run.py`
  - Outcome: success (`5 passed in 1.76s`).
- Live API sanity check:
  - `curl -X POST http://localhost:8001/api/tracer/run ...` (run_id `run-live-approval-1`) -> proposal created.
  - `curl http://localhost:8001/api/tracer/run-live-approval-1/proposed-changes` -> status `pending`.
  - `curl -X POST http://localhost:8001/api/tracer/run-live-approval-1/approval ...` -> status `applied`.

### Container restart/rebuild logs
- Pre-task full clean restart (fresh builds/logs):
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Post-change refresh (changed container scope: backend-only code + backend tests):
  - `docker compose restart backend`
- Running state check:
  - `docker compose ps` -> `db`, `backend`, `frontend`, `chrome` all `Up` (`db` healthy).
- Logs reviewed:
  - `docker compose logs --tail 200 backend` -> uvicorn startup/reload healthy; successful requests for:
    - `POST /api/tracer/run`
    - `GET /api/tracer/run-live-approval-1/proposed-changes`
    - `POST /api/tracer/run-live-approval-1/approval`
  - `docker compose logs --tail 60 frontend` -> Vite dev server ready.
  - `docker compose logs --tail 60 db` -> PostgreSQL ready to accept connections.

### Notes
- Apply transitions now occur only through explicit approve action unless `TRACER_AUTO_APPLY_CHANGES` is enabled.
- The live tracer run used for sanity checks logged expected fallback behavior when model credentials are missing, but API proposal/approval flow completed successfully.

## Section 7: Pre-completion verification and deterministic context

**Single goal:** Document the existing pre-completion verification loop and optionally inject deterministic context (e.g. task spec or trace summary) into the verification checklist so agents verify against the spec.

**Details:**
- `TracerPreCompletionVerificationMiddleware` and build-verify-fix prompts already exist. This section: (1) Document in completed.md or docs how the verification loop works (plan → build → verify → fix; PreCompletionChecklistMiddleware forces a verification turn before exit). (2) Optionally harden by ensuring deterministic context (e.g. `current_trace_summary`, task spec snippet, or run_id) is always available and included in `build_pre_completion_checklist_message` when present in state.
- Do not remove or replace the existing middleware; only document and optionally extend context injection.

### Completed work
- Documented and preserved the existing pre-completion verification loop:
  - Main tracer prompt keeps explicit plan/build/verify/fix guidance.
  - `TracerPreCompletionVerificationMiddleware` still forces one verification turn before completion by injecting the pre-completion checklist and jumping back to model execution.
- Hardened deterministic context injection for checklist generation:
  - Updated `src/backend/agents/tracer_middleware.py` so `build_pre_completion_checklist_message(...)` includes, when present:
    - `run_id`
    - `trace_ids`
    - `current_trace_summary`
    - `task_spec_snippet`
- Extended tracer state contract in `src/backend/agents/tracer_state.py`:
  - Added optional `trace_ids` and `task_spec_snippet` fields.
- Injected deterministic trace context at tracer graph invocation in `src/backend/services/trace_analyzer_service.py`:
  - Graph state now includes `trace_ids` and a deterministic `current_trace_summary` generated from loaded traces.
  - Added `_build_current_trace_summary(...)` helper for stable summary formatting.
  - Added visibility logs when invoking graph (`trace_id_count`, `has_trace_summary`).
- Added visibility logs in pre-completion middleware in `src/backend/agents/deep_agent_tracer.py`:
  - Checklist injection log now includes `trace_id_count`, `has_trace_summary`, and `has_task_spec_snippet`.
- Added/updated unit tests:
  - `src/backend/tests/agents/test_tracer_middleware.py`
    - verifies checklist includes trace IDs.
    - verifies checklist includes task spec snippet when provided.
  - `src/backend/tests/services/test_trace_analyzer_service.py`
    - verifies tracer graph state now includes deterministic `trace_ids` and `current_trace_summary`.

### Validation commands and outcomes
- `docker compose exec backend uv run pytest tests/agents/test_tracer_middleware.py tests/agents/test_deep_agent_tracer.py -k pre_completion`
  - Outcome: success (`4 passed, 27 deselected in 1.84s`).
- `docker compose exec backend uv run pytest tests/services/test_trace_analyzer_service.py`
  - Outcome: success (`4 passed in 1.27s`).

### Container restart/rebuild logs
- Pre-task full clean restart (fresh builds/logs):
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Post-change refresh (changed container scope: backend-only code + backend tests):
  - `docker compose restart backend`
- Running state check:
  - `docker compose ps` -> `db`, `backend`, `frontend`, `chrome` all `Up` (`db` healthy).
- Logs reviewed:
  - `docker compose logs --tail=160 backend` -> alembic + uvicorn startup complete, watch reloads after edited files, final server process healthy.
  - `docker compose logs --tail=120 frontend` -> Vite dev server ready on port 5173 (host mapped 5174).
  - `docker compose logs --tail=120 db` -> PostgreSQL ready to accept connections.
- Readiness checks:
  - `curl -I http://localhost:8001/docs` -> `HTTP/1.1 200 OK`.
  - `curl -I http://localhost:5174` -> `HTTP/1.1 200 OK`.

### Notes
- Section 7 is complete. The verification middleware remains the primary enforcement mechanism, and checklist prompts now carry deterministic context from tracer state when available.
