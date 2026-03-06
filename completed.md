## Section 1: Langfuse trace ingestion

**Depends on:** None.

**Single goal:** Ingest traces from Langfuse for a given run or experiment so the tracer can analyze errors.

**Deep-agent capability:** Trace Analyzer Skill (data input); tools & context (traces as observation for the tracer).

**Details implemented:**
- Added `src/backend/services/langfuse_trace_service.py` to fetch traces from Langfuse by explicit `trace_ids` or list filters (`run_name`, `from_timestamp`, `to_timestamp`, `limit`, environment).
- Added normalization into strongly typed models in `src/backend/schemas/trace.py` for traces, spans, errors, latency, usage/tokens, and costs.
- Added structured service logging for disabled-mode short-circuit, client initialization/fetch/list counts, and normalized trace metadata.
- Added unit coverage in `src/backend/tests/services/test_langfuse_trace_service.py` for trace-id fetch, list/filter behavior, and disabled mode.
- Updated backend dependencies/config: `langfuse` in `src/backend/pyproject.toml`, refreshed `src/backend/uv.lock`, and set pytest pythonpath for consistent module imports in container.

**Test results:**
- `docker compose exec backend uv run pytest tests/services/test_langfuse_trace_service.py`
- Result: `3 passed in 0.13s` on 2026-03-06.

**Useful logs (2026-03-06):**
- Backend:
  - `INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.`
  - `INFO:     Uvicorn running on http://0.0.0.0:8000`
  - `INFO:     Application startup complete.`
- Frontend:
  - `VITE v7.3.1 ready in 469 ms`
  - `Local: http://localhost:5173/`
- DB:
  - `database system is ready to accept connections`

**Operational note:**
- During fresh bootstrap, backend initially failed because Alembic targeted `agent_trace` while Postgres initialized `agent_search` from `.env`; created missing DB `agent_trace` and restarted backend successfully.

## Section 2: Trace schema and storage for analysis

**Depends on:** Section 1 (ingestion and normalized schema).

**Single goal:** Define a persistent schema for traces and store ingested traces so the tracer and parallel analyzers can query them.

**Deep-agent capability:** Context/trace persistence; enables tracer and subagents to load traces by run/experiment.

**Details implemented:**
- Added SQLAlchemy ORM models in `src/backend/models.py` for `traces` and `trace_spans` including run/experiment identifiers, span payloads, tool calls, error summaries, token/cost fields, timestamps, and optional raw payload storage.
- Added DB session utilities in `src/backend/db.py`.
- Added Alembic migration `src/backend/alembic/versions/20260306_01_add_trace_tables.py` with upgrade/downgrade for both trace tables and indexes.
- Updated Alembic runtime config in `src/backend/alembic/env.py` to load metadata from ORM models and honor `DATABASE_URL` from environment.
- Extended trace schemas in `src/backend/schemas/trace.py` with `TraceStorageQuery` and `StoredTrace`.
- Added `src/backend/services/trace_storage_service.py` with save/load APIs for traces by `run_id`, `experiment_name`, or explicit `trace_ids`, including upsert behavior and structured logging.
- Added unit coverage in `src/backend/tests/services/test_trace_storage_service.py` for round-trip persistence, upsert behavior, and query filtering.

**Test results:**
- `docker compose exec backend uv run alembic downgrade base && docker compose exec backend uv run alembic upgrade head && docker compose exec backend uv run alembic current`
- Result: downgrade/upgrade successful; current revision `20260306_01 (head)` on 2026-03-06.
- `docker compose exec backend uv run pytest tests/services/test_langfuse_trace_service.py tests/services/test_trace_storage_service.py`
- Result: `6 passed in 0.54s` on 2026-03-06.

**Useful logs (2026-03-06):**
- Backend:
  - `INFO  [alembic.runtime.migration] Running upgrade  -> 20260306_01, add trace storage tables`
  - `INFO:     Uvicorn running on http://0.0.0.0:8000`
  - `INFO:     Application startup complete.`
- DB:
  - `List of relations: alembic_version, trace_spans, traces`
- Frontend:
  - `VITE v7.3.1  ready in 373 ms`

**Operational note:**
- Earlier startup failures in this loop showed `database "agent_trace" does not exist`; this was addressed by making Alembic use the container `DATABASE_URL` from environment so startup and migrations align with configured DB name.

## Section 3: Sandbox runtime for target repo

**Depends on:** None.

**Single goal:** Provide an isolated environment (sandbox) where the target agent’s repo is cloned and all tracer-driven edits and commands run. When no URL is supplied by the caller, use the configured default.

**Deep-agent capability:** Code execution environment; virtual filesystem backend (sandbox as pluggable backend for list/read/edit/execute).

**Details implemented:**
- Added `src/backend/schemas/sandbox.py` with typed schemas for sandbox creation/session metadata and command request/result payloads.
- Added `src/backend/services/sandbox_service.py` implementing disposable sandbox lifecycle with `git clone`, sandbox-scoped command execution, sandbox-relative read/write operations, patch-by-replace helper, path-escape protection, and teardown.
- Implemented default target repo fallback from `TRACER_DEFAULT_TARGET_REPO_URL` when `target_repo_url` is omitted.
- Added structured logging around sandbox create/clone/command/read/write/teardown for operational visibility.
- Added `src/backend/tests/services/test_sandbox_service.py` covering default URL fallback, write/read/command flow, path containment enforcement, and teardown cleanup with mocked cloning (no network dependency).
- Verified `.env.example` already contains `TRACER_DEFAULT_TARGET_REPO_URL=https://github.com/Nickbohm555/agent-search`.

**Test results:**
- `docker compose exec backend uv run pytest tests/services/test_sandbox_service.py`
- Result: `3 passed in 0.12s` on 2026-03-06.

**Useful logs (2026-03-06):**
- Backend:
  - `INFO  [alembic.runtime.migration] Running upgrade  -> 20260306_01, add trace storage tables`
  - `INFO:     Uvicorn running on http://0.0.0.0:8000`
  - `WARNING:  WatchFiles detected changes in 'tests/services/test_sandbox_service.py', 'services/sandbox_service.py', 'schemas/sandbox.py'. Reloading...`
  - `INFO:     Application startup complete.`
- Frontend:
  - `VITE v7.3.1  ready in 164 ms`
  - `Local: http://localhost:5173/`
- DB:
  - `database system is ready to accept connections`

**Operational note:**
- Changed container: `backend` (code and tests only). Restarted `backend` and verified `backend`, `frontend`, and `db` logs after restart.

## Section 4: LangGraph tracer deep-agent graph skeleton

**Depends on:** None (foundation for Sections 5–15).

**Single goal:** Implement the tracer as a LangGraph **deep-agent** graph with entry, agent node(s), and conditional edges. **Do not add tools or middleware in this section**—only the graph backbone.

**Deep-agent capability:** Planning (graph backbone); ReAct-style agent loop with shared state and conditional routing (continue vs end).

**Details implemented:**
- Added backend dependencies in `src/backend/pyproject.toml` and refreshed `src/backend/uv.lock`: `langgraph`, `langchain-core`, `langchain-openai`.
- Added tracer graph state schema in `src/backend/agents/tracer_state.py` with `messages`, `current_trace_summary`, and `run_id`.
- Implemented `src/backend/agents/langgraph_agent.py` skeleton with:
  - `StateGraph` backbone (`START -> agent -> conditional -> END|agent`).
  - `should_continue` conditional routing based on `tool_calls` in the last AI message.
  - Minimal default agent node with no tools/middleware attached.
- Added unit tests in `src/backend/tests/agents/test_langgraph_agent.py` for conditional routing and single-step default graph execution.
- Added structured logging in graph helpers for node execution and route decisions.

**Test results:**
- `docker compose exec backend uv run pytest tests/agents/test_langgraph_agent.py`
- Result: `2 passed in 0.33s` on 2026-03-06.

**Useful logs (2026-03-06):**
- Backend:
  - `INFO:     Uvicorn running on http://0.0.0.0:8000`
  - `INFO:     Application startup complete.`
  - `WARNING:  WatchFiles detected changes ... Reloading...` (expected after dependency sync and file updates)
- Frontend:
  - `VITE v7.3.1  ready in 193 ms`
  - `Local: http://localhost:5173/`
- DB:
  - `database system is ready to accept connections`

**Operational note:**
- Changed container: `backend`. Restarted `backend` after implementation and verified `docker compose ps` plus backend/frontend/db logs.

## Section 5: Reasoning budget configuration

**Depends on:** Section 4 (graph exists to receive config).

**Single goal:** Make reasoning compute configurable (e.g. high for planning and verification, lower for implementation) to balance quality and token/time (per article “reasoning sandwich”).

**Deep-agent capability:** Context and token management — reasoning budget; configurable reasoning level and optional “reasoning sandwich.”

**Details implemented:**
- Added `src/backend/agents/tracer_config.py` with phase-aware reasoning configuration (`planning`, `implementation`, `verification`) and reasoning levels (`low`, `medium`, `high`, `xhigh`).
- Implemented default “reasoning sandwich” mapping (`xhigh`–`high`–`xhigh`) plus run-level override parsing via `TracerReasoningConfig.from_run_config(...)`.
- Added robust coercion/validation helpers for reasoning phase and level with warning logs on invalid inputs.
- Extended `src/backend/agents/tracer_state.py` with optional reasoning fields (`reasoning_phase`, `reasoning_level`, `reasoning_phase_levels`).
- Updated `src/backend/agents/langgraph_agent.py` to resolve phase + effective reasoning budget per invocation and pass it to an abstract model adapter hook (`model_invoke`) so different backends can honor settings.
- Added structured logging in agent execution for resolved reasoning configuration visibility.
- Expanded tests in `src/backend/tests/agents/test_langgraph_agent.py` to verify phase-budget mapping and state-level override behavior.
- Added `src/backend/tests/agents/test_tracer_config.py` for default mapping, run-config overrides, and invalid phase fallback.

**Test results:**
- `docker compose exec backend uv run pytest tests/agents/test_langgraph_agent.py tests/agents/test_tracer_config.py`
- Result: `7 passed in 0.35s` on 2026-03-06.

**Useful logs (2026-03-06):**
- Backend:
  - `INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.`
  - `INFO:     Uvicorn running on http://0.0.0.0:8000`
  - `INFO:     Application startup complete.`
  - `WARNING:  WatchFiles detected changes in 'agents/tracer_config.py'. Reloading...` (expected during iteration)
- Frontend:
  - `VITE v7.3.1  ready in 190 ms`
  - `Local: http://localhost:5173/`
- DB:
  - `database system is ready to accept connections`

**Operational note:**
- Changed container: `backend`.
- Restarted backend with `docker compose restart backend` and verified logs for `backend`, `frontend`, and `db` plus `docker compose ps` healthy status.
