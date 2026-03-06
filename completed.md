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
