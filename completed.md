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
