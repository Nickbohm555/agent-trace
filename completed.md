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
