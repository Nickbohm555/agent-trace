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

## Section 6: Tracer tool – read trace

**Depends on:** Sections 1, 2 (ingestion and storage), Section 4 (graph to bind tool).

**Single goal:** Add a tool the tracer agent can call to read fetched trace content (errors, spans, inputs/outputs).

**Deep-agent capability:** Tools — trace read (observation/feedback signal for the tracer).

**Details implemented:**
- Added `src/backend/tools/trace_tools.py` with a `read_trace` structured tool that accepts `run_id` and/or `trace_id`, clamps query `limit`, and returns structured summaries (errors, failed spans, key inputs/outputs, token/cost/latency metadata).
- Added logging in the tool for invalid input calls and successful read summaries (`run_id`, `trace_id`, requested/effective limit, returned trace count).
- Updated `src/backend/agents/langgraph_agent.py` to support tool binding via LangGraph `ToolNode` and route `agent -> tools -> agent` when tool calls are present.
- Bound `read_trace` automatically when `trace_storage_service` is supplied to graph construction, while keeping no-tools behavior unchanged.
- Updated `src/backend/tools/__init__.py` exports for trace tool discovery.
- Added unit tests in `src/backend/tests/tools/test_trace_tools.py` for validation errors and structured trace-summary output.
- Added graph integration coverage in `src/backend/tests/agents/test_langgraph_agent.py` to verify tool call execution and post-tool reasoning loop.

**Test results:**
- `docker compose exec backend uv run pytest tests/tools/test_trace_tools.py tests/agents/test_langgraph_agent.py`
- Result: `7 passed in 0.93s` on 2026-03-06.

**Useful logs (2026-03-06):**
- Backend:
  - `INFO  [alembic.runtime.migration] Running upgrade  -> 20260306_01, add trace storage tables`
  - `INFO:     Uvicorn running on http://0.0.0.0:8000`
  - `WARNING:  WatchFiles detected changes in 'tools/trace_tools.py'. Reloading...`
  - `INFO:     Application startup complete.`
- Frontend:
  - `VITE v7.3.1  ready in 161 ms`
  - `Local: http://localhost:5173/`
- DB:
  - `database system is ready to accept connections`
- Backend readiness check:
  - `curl -I http://localhost:8001/docs` returned `HTTP/1.1 200 OK`

**Operational note:**
- Changed container: `backend`.
- Restarted backend with `docker compose restart backend` after implementation and verified `docker compose ps` plus logs for `backend`, `frontend`, and `db`.

## Section 7: Tracer tools - list and read codebase

**Depends on:** Section 3 (sandbox), Section 4 (graph).

**Single goal:** Give the tracer agent tools to list directories and read files in the sandboxed target repo.

**Deep-agent capability:** Virtual filesystem - list directory, read file (with sandbox root).

**Details implemented:**
- Added sandbox-backed listing support in `src/backend/services/sandbox_service.py`:
  - `list_directory(session, path)` to enumerate repo-relative entries with metadata.
  - `list_directory_by_sandbox_path(...)` and `read_file_by_sandbox_path(...)` adapters so tool calls can operate from `sandbox_path`.
  - Structured logging for directory listing and path-resolved file reads.
- Added `src/backend/tools/codebase_tools.py` with structured tools:
  - `list_directory(sandbox_path, path='.')`
  - `read_file(sandbox_path, path)`
  Both are wired through `SandboxService` so filesystem access stays sandbox-scoped.
- Updated `src/backend/agents/langgraph_agent.py` to bind codebase tools when `sandbox_service` is provided.
- Updated `src/backend/tools/__init__.py` exports for codebase tool builders.
- Expanded tests:
  - `src/backend/tests/tools/test_codebase_tools.py` (unit tests for list/read tool behavior with mocked clone)
  - `src/backend/tests/services/test_sandbox_service.py` (covers list behavior in sandbox service flow)
  - `src/backend/tests/agents/test_langgraph_agent.py` (integration loop where agent calls `list_directory` then `read_file` via ToolNode)

**Test results:**
- `docker compose exec backend uv run pytest tests/tools/test_codebase_tools.py tests/services/test_sandbox_service.py tests/agents/test_langgraph_agent.py`
- Result: `11 passed in 0.87s` on 2026-03-06.

**Useful logs (2026-03-06):**
- `docker compose ps` after restart:
  - `backend` up on `0.0.0.0:8001->8000/tcp`
  - `frontend` up on `0.0.0.0:5174->5173/tcp`
  - `db` healthy on `0.0.0.0:5433->5432/tcp`
- Backend logs:
  - `INFO: Uvicorn running on http://0.0.0.0:8000`
  - `INFO: Application startup complete.`
  - `WARNING: WatchFiles detected changes ... Reloading...` (expected during iteration)
- Frontend logs:
  - `VITE v7.3.1 ready`
  - `Local: http://localhost:5173/`
- DB logs:
  - `database system is ready to accept connections`

**Operational note:**
- Changed container: `backend`.
- Per iteration policy, restarted `backend` (`docker compose restart backend`) and re-checked backend/frontend/db logs.

## Section 8: Tracer tool – edit file in sandbox

**Depends on:** Section 3 (sandbox), Section 4 (graph). Same module as Section 7 for codebase tools.

**Single goal:** Add a tool for the tracer to apply edits (patch or full replace) to files in the sandboxed repo.

**Deep-agent capability:** Virtual filesystem — edit_file / write_file (all writes scoped to sandbox).

**Details implemented:**
- Added `edit_file` in `src/backend/tools/codebase_tools.py` as a structured tool (`edit_file(sandbox_path, path, content)`) backed by sandbox write operations.
- Added sandbox adapter method `write_file_by_sandbox_path(...)` in `src/backend/services/sandbox_service.py` so tool calls can write via active sandbox root safely.
- Bound `edit_file` into tracer graph tool registration in `src/backend/agents/langgraph_agent.py` alongside `list_directory` and `read_file`.
- Updated tool exports in `src/backend/tools/__init__.py` to include `build_edit_file_tool`.
- Added unit coverage in `src/backend/tests/tools/test_codebase_tools.py` to assert `edit_file` updates file content and read-back reflects the edit.
- Extended integration coverage in `src/backend/tests/agents/test_langgraph_agent.py` so the graph loop executes `list_directory -> edit_file -> read_file` and verifies updated content.

**Test results:**
- `docker compose exec backend uv run pytest tests/tools/test_codebase_tools.py tests/agents/test_langgraph_agent.py`
- Result: `9 passed in 1.02s` on 2026-03-06.

**Useful logs (2026-03-06):**
- `docker compose ps` after restart:
  - `backend` up on `0.0.0.0:8001->8000/tcp`
  - `frontend` up on `0.0.0.0:5174->5173/tcp`
  - `db` healthy on `0.0.0.0:5433->5432/tcp`
- Backend logs:
  - `INFO: Uvicorn running on http://0.0.0.0:8000`
  - `INFO: Application startup complete.`
  - `WARNING: WatchFiles detected changes ... Reloading...` (expected during iteration)
- Frontend logs:
  - `VITE v7.3.1 ready in 234 ms`
  - `Local: http://localhost:5173/`
- DB logs:
  - `database system is ready to accept connections`

**Operational note:**
- Changed container: `backend`.
- Restarted backend with `docker compose restart backend` and verified logs for `backend`, `frontend`, and `db`.
- Initial parallel attempt restarted backend while tests were running and returned exit code `137`; tests were re-run cleanly and passed.

## Section 9: Tracer tool – run command in sandbox

**Depends on:** Section 3 (sandbox), Section 4 (graph).

**Single goal:** Add a tool for the tracer to run shell commands (e.g. tests, linters) inside the sandbox.

**Deep-agent capability:** Code execution — execute tool (run command in isolated sandbox; stdout/stderr, exit code, timeout).

**Details implemented:**
- Added `src/backend/tools/sandbox_tools.py` with `run_command(sandbox_path, command, timeout_seconds, cwd)` as a structured tool.
- Added `SandboxService.run_command_by_sandbox_path(...)` in `src/backend/services/sandbox_service.py` so command execution is resolved and executed from sandbox context only.
- Bound `run_command` to the tracer graph in `src/backend/agents/langgraph_agent.py` when `sandbox_service` is provided.
- Exported the new tool builder from `src/backend/tools/__init__.py`.
- Added unit coverage in `src/backend/tests/tools/test_sandbox_tools.py` for `echo` execution and stdout/exit-code assertions.
- Added graph integration coverage in `src/backend/tests/agents/test_langgraph_agent.py` so the agent invokes `run_command` and validates tool output from `ToolMessage`.
- Added structured logs in the tool for visibility (`sandbox_path`, command, cwd, timeout, exit_code, stdout/stderr sizes).

**Test results:**
- `docker compose exec backend uv run pytest tests/tools/test_sandbox_tools.py tests/agents/test_langgraph_agent.py`
- Result: `8 passed in 1.60s` on 2026-03-06.

**Useful logs (2026-03-06):**
- Fresh full restart executed before implementation:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Backend logs:
  - `INFO  [alembic.runtime.migration] Running upgrade  -> 20260306_01, add trace storage tables`
  - `INFO:     Uvicorn running on http://0.0.0.0:8000`
  - `INFO:     Application startup complete.`
  - `WARNING:  WatchFiles detected changes in 'tools/sandbox_tools.py'. Reloading...` (expected during iteration)
- Frontend logs:
  - `VITE v7.3.1  ready in 6213 ms`
  - `Local: http://localhost:5173/`
- DB logs:
  - `database system is ready to accept connections`
- Readiness check:
  - `curl http://localhost:8001/docs` returned `200`.

**Operational note:**
- Changed container: `backend`.
- Restarted backend after implementation (`docker compose restart backend`) and verified `docker compose ps` plus logs for `backend`, `frontend`, `db`, and `chrome`.

## Section 10: Tracer system prompt – plan, build, verify, fix

**Depends on:** Section 4 (graph to inject prompt).

**Single goal:** Implement the tracer’s system prompt with Planning & Discovery, Build, Verify, Fix and a strong focus on testing (per article).

**Deep-agent capability:** System prompts — plan–build–verify–fix; self-verification and testing as first-class phases.

**Details implemented:**
- Added `src/backend/agents/tracer_prompts.py` with a dedicated tracer system prompt builder containing explicit `Planning & Discovery`, `Build`, `Verify`, and `Fix` phases.
- Included verification guidance that requires checking outputs against the requested task specification (not against agent-written code assumptions).
- Updated `src/backend/agents/langgraph_agent.py` to load and inject the tracer system prompt into agent state as a `SystemMessage` before model invocation.
- Preserved existing graph/tool architecture; prompt injection is additive and isolated to configured agent execution.
- Added prompt-coverage tests in `src/backend/tests/agents/test_tracer_prompts.py`.
- Added graph behavior test in `src/backend/tests/agents/test_langgraph_agent.py` to assert system prompt injection into the model adapter state.

**Test results:**
- `docker compose exec backend uv run pytest tests/agents/test_langgraph_agent.py tests/agents/test_tracer_prompts.py`
- Result: `10 passed in 1.30s` on 2026-03-06.

**Useful logs (2026-03-06):**
- Full app fresh restart completed before work:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Backend:
  - `INFO  [alembic.runtime.migration] Running upgrade  -> 20260306_01, add trace storage tables`
  - `INFO:     Uvicorn running on http://0.0.0.0:8000`
  - `INFO:     Application startup complete.`
  - `WARNING:  WatchFiles detected changes in 'agents/tracer_prompts.py'. Reloading...` (expected during iteration)
- Frontend:
  - `VITE v7.3.1  ready in 772 ms`
  - `Local: http://localhost:5173/`
- DB:
  - `database system is ready to accept connections`

**Operational note:**
- Changed container: `backend`.
- Restarted backend (`docker compose restart backend`) after implementation and re-checked `docker compose ps` plus backend/frontend/db logs.

## Section 11: Teaching testable code in tracer prompt

**Depends on:** Section 10 (existing system prompt to extend).

**Single goal:** Add prompt instructions that work will be measured against programmatic tests, file paths must be exact, and edge cases matter (per article).

**Deep-agent capability:** System prompts — testable code, exact file paths, edge cases (not only happy path).

**Details implemented:**
- Extended `src/backend/agents/tracer_prompts.py` with a focused `Testable Code expectations` fragment instead of duplicating the full prompt.
- Added explicit guidance that outcomes are measured by programmatic tests.
- Added explicit guidance to follow task-spec file paths exactly and avoid relocating requested changes.
- Strengthened edge-case requirement by stating edge cases are first-class requirements.
- Added prompt tests in `src/backend/tests/agents/test_tracer_prompts.py` to assert all three instructions are present.

**Test results:**
- `docker compose exec backend uv run pytest tests/agents/test_tracer_prompts.py`
- Result: `3 passed in 0.01s` on 2026-03-06.

**Useful logs (2026-03-06):**
- Full clean restart completed before implementation:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- `docker compose ps` after restart:
  - `backend` up on `0.0.0.0:8001->8000/tcp`
  - `frontend` up on `0.0.0.0:5174->5173/tcp`
  - `db` healthy on `0.0.0.0:5433->5432/tcp`
- Backend logs:
  - `INFO  [alembic.runtime.migration] Running upgrade  -> 20260306_01, add trace storage tables`
  - `INFO:     Uvicorn running on http://0.0.0.0:8000`
  - `INFO:     Application startup complete.`
  - `WARNING:  WatchFiles detected changes in 'agents/tracer_prompts.py'. Reloading...` (expected)
- Frontend logs:
  - `VITE v7.3.1 ready in 1229 ms`
  - `Local: http://localhost:5173/`
- DB logs:
  - `database system is ready to accept connections`

**Operational note:**
- Changed container: `backend`.
- Restarted backend with `docker compose restart backend` after implementation and re-checked backend/frontend/db logs.

## Section 12: Local context injection for tracer

**Depends on:** Section 3 (sandbox), Section 4 (graph).

**Single goal:** On tracer start, inject context about the sandbox environment: cwd, directory map, and available tools (e.g. Python path, key binaries).

**Deep-agent capability:** Context management — local context injection (LocalContextMiddleware; onboard agent into environment).

**Details implemented:**
- Added `src/backend/agents/tracer_context.py` with sandbox discovery helpers to build a structured local context payload at run start.
- Context now includes sandbox cwd, top-level directory map, and tool path detection (`python3`, `python`, `pytest`, `node`, `npm`, `git`, `uv`) via sandbox-scoped commands.
- Extended `src/backend/agents/tracer_state.py` with `sandbox_path` and `local_context` fields so context can be injected once and persisted in state.
- Updated `src/backend/agents/langgraph_agent.py` to:
  - inject local context as a system message when `sandbox_path` is provided,
  - persist generated local context in state,
  - preserve prompt injection by checking for actual tracer system prompt content (fixes collision with context system messages),
  - add logging for local-context generation/injection.
- Added tests in `src/backend/tests/agents/test_tracer_context.py` for context builder output and marker detection.
- Extended `src/backend/tests/agents/test_langgraph_agent.py` with integration coverage verifying first-turn local context injection into model-visible state.

**Test results:**
- `docker compose exec backend uv run pytest tests/agents/test_tracer_context.py tests/agents/test_langgraph_agent.py`
- Result: `11 passed in 0.94s` on 2026-03-06.

**Useful logs (2026-03-06):**
- `docker compose restart backend` completed successfully; `docker compose ps` shows `backend`, `frontend`, `db`, and `chrome` running (`db` healthy).
- Backend logs:
  - `INFO:     Uvicorn running on http://0.0.0.0:8000`
  - `INFO:     Application startup complete.`
  - `WARNING:  WatchFiles detected changes in 'agents/tracer_context.py'. Reloading...` (expected during iteration)
- Frontend logs:
  - `VITE v7.3.1 ready in 436 ms`
  - `Local: http://localhost:5173/`
- DB logs:
  - `database system is ready to accept connections`

**Operational note:**
- Changed container: `backend`.
- Full clean restart was completed before implementation (`docker compose down -v --rmi all && docker compose build && docker compose up -d`).
- Post-change restart performed for `backend` and logs were reviewed for `backend`, `frontend`, and `db`.

## Section 13: Pre-completion verification middleware

**Depends on:** Section 4 (graph to attach middleware).

**Single goal:** Before the tracer can “finish”, run a verification pass (e.g. remind agent to run tests and compare to spec) so the agent does not exit after “code looks ok” without testing.

**Deep-agent capability:** Middleware — pre-completion verification (PreCompletionChecklistMiddleware / Ralph Wiggum–style loop).

**Details implemented:**
- Added `src/backend/agents/tracer_middleware.py` with:
  - `should_inject_pre_completion_checklist(...)` to detect first end-attempt without prior verification.
  - `build_pre_completion_checklist_message(...)` to inject a concrete verification checklist (tests + spec comparison).
  - `pre_completion_check_node(...)` to append the checklist and mark state as verified.
- Extended `src/backend/agents/tracer_state.py` with `pre_completion_verified` flag.
- Updated `src/backend/agents/langgraph_agent.py` conditional routing:
  - `continue` when tool calls are present.
  - `verify` route before `END` when no tool calls and verification has not yet occurred.
  - Added `pre_completion_check` node and edge back to `agent`, forcing one extra verification turn before completion.
- Updated existing graph tests in `src/backend/tests/agents/test_langgraph_agent.py` for new route behavior and added a dedicated route assertion for `verify`.
- Added `src/backend/tests/agents/test_tracer_middleware.py` to validate middleware helpers and the forced one-more-turn verification loop.
- Added logging for route selection and checklist injection for runtime visibility.

**Test results:**
- `docker compose exec backend uv run pytest tests/agents/test_langgraph_agent.py tests/agents/test_tracer_middleware.py`
- Result: `13 passed in 1.71s` on 2026-03-06.

**Useful logs (2026-03-06):**
- Container health after backend restart (`docker compose ps`):
  - `backend` up on `0.0.0.0:8001->8000/tcp`
  - `frontend` up on `0.0.0.0:5174->5173/tcp`
  - `db` healthy on `0.0.0.0:5433->5432/tcp`
- Backend logs (`docker compose logs --tail=120 backend`):
  - `INFO: Uvicorn running on http://0.0.0.0:8000`
  - `INFO: Application startup complete.`
  - `WARNING: WatchFiles detected changes ... Reloading...` (expected during iteration)
- Frontend logs (`docker compose logs --tail=80 frontend`):
  - `VITE v7.3.1 ready`
  - `Local: http://localhost:5173/`
- DB logs (`docker compose logs --tail=80 db`):
  - `database system is ready to accept connections`
- Backend readiness:
  - Initial post-restart probe returned `000` during startup.
  - Recheck succeeded: `curl http://localhost:8001/docs` returned `HTTP/1.1 200 OK`.

**Operational note:**
- Changed container: `backend` only (Python code/tests).
- Restarted backend with `docker compose restart backend` and verified backend/frontend/db logs plus readiness endpoint.

## Section 14: Time budget injection

**Depends on:** Section 4 (graph to inject into state).

**Single goal:** Inject time-remaining (or step-remaining) warnings into the tracer’s context so the agent shifts to verification and submission under limits.

**Deep-agent capability:** Context management / middleware — time budget injection (nudge toward verification and submit).

**Details implemented:**
- Extended `src/backend/agents/tracer_state.py` with time-budget state fields: `run_started_at_epoch_seconds`, `max_runtime_seconds`, `max_steps`, `time_budget_notice_interval_steps`, `agent_step_count`, and `time_budget_last_notice_step`.
- Added Section 14 middleware in `src/backend/agents/tracer_middleware.py`:
  - `apply_time_budget_injection(...)` to increment step count, initialize run start time, and periodically decide whether to inject a budget warning.
  - `build_time_budget_message(...)` to generate a concise runtime/step-remaining message that nudges verification and submission.
  - Configured trigger conditions for periodic notices (`time_budget_notice_interval_steps`, default `3`) plus near-limit warnings (`<=2` steps remaining or `<=120s` runtime remaining).
  - Added structured logging when budget context is injected.
- Wired time-budget injection into `src/backend/agents/langgraph_agent.py` before model invocation:
  - Agent now evaluates budget context each turn and appends a `SystemMessage` budget warning when applicable.
  - Budget warning is persisted to graph state/messages so the run transcript captures visibility.
  - Agent step/time state is persisted on each turn.
- Added tests:
  - `src/backend/tests/agents/test_tracer_middleware.py` now validates direct short-budget injection and runtime/step formatting.
  - `src/backend/tests/agents/test_langgraph_agent.py` now validates graph-level injection with `max_steps=1` and confirms message presence in model-visible state and final graph state.

**Test results:**
- `docker compose exec backend uv run pytest tests/agents/test_tracer_middleware.py tests/agents/test_langgraph_agent.py`
- Result: `16 passed in 1.10s` on 2026-03-06.

**Useful logs (2026-03-06):**
- Clean start performed before implementation:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Post-restart container state (`docker compose ps`):
  - `backend` up on `0.0.0.0:8001->8000/tcp`
  - `frontend` up on `0.0.0.0:5174->5173/tcp`
  - `db` healthy on `0.0.0.0:5433->5432/tcp`
- Backend logs (`docker compose logs --tail=200 backend`):
  - `INFO  [alembic.runtime.migration] Running upgrade  -> 20260306_01, add trace storage tables`
  - `INFO:     Uvicorn running on http://0.0.0.0:8000`
  - `INFO:     Application startup complete.`
  - `WARNING:  WatchFiles detected changes ... Reloading...` (expected during iterative edits)
- Frontend logs (`docker compose logs --tail=60 frontend`):
  - `VITE v7.3.1 ready`
  - `Local: http://localhost:5173/`
- DB logs (`docker compose logs --tail=80 db`):
  - `database system is ready to accept connections`
- Backend readiness check:
  - `curl http://localhost:8001/docs` returned HTTP `200`.

**Operational note:**
- Changed container: `backend`.
- Restarted changed service with `docker compose restart backend` and reviewed backend/frontend/db logs after restart.
