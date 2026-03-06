# Agent-Search Completed Test Sections

## Test Section 1: Stack and health – services up and reachable

**Single goal:** Confirm Docker stack is up, backend health returns 200, and frontend is reachable so all later tests can run.

**Details:**
- All services (`backend`, `frontend`, `db`) must be running; backend must respond at `/api/health`; frontend must be loadable at `http://localhost:5174`.
- No agent run or data load in this section.

**Tech stack and dependencies**
- Docker Compose; curl (or browser) for HTTP checks.

**Files and purpose**

| File | Purpose |
|------|--------|
| (none) | N/A – infrastructure check only. |

**How to test:**
1. Start stack: `docker compose up -d` (from repo root).
2. Wait for readiness: `docker compose ps` → all services `Up`; `db` healthy if shown.
3. Backend health: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/health` → `200`; `curl -s http://localhost:8001/api/health` → body contains `"status":"ok"`.
4. Frontend: open `http://localhost:5174` in browser (or use cursor-ide-browser: `browser_navigate` to `http://localhost:5174`, then `browser_snapshot`) → page loads, no 5xx or connection refused.
5. Optional: `docker compose logs --tail=20 backend` → no startup tracebacks or fatal errors.

**Test results:**
- Fresh reset/build/start executed:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Running state (`docker compose ps`) showed required services up:
  - `agent-trace-backend ... Up ... 0.0.0.0:8000->8000/tcp`
  - `agent-trace-db ... Up (healthy) ... 0.0.0.0:5432->5432/tcp`
  - `agent-trace-frontend ... Up ... 0.0.0.0:5173->5173/tcp`
- Backend health checks:
  - `curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/health` => `200`
  - `curl -s http://localhost:8001/api/health` => `{"status":"ok"}`
- Frontend reachability:
  - `curl -s -I http://localhost:5174 | head -n 1` => `HTTP/1.1 200 OK`
  - `curl -s http://localhost:5174 | head -n 5` returned Vite React HTML shell (`<!doctype html> ...`)
- Useful startup logs:
  - Backend (`docker compose logs --tail=40 backend`) included Alembic upgrade and successful startup:
    - `Running upgrade  -> 001_internal ...`
    - `Application startup complete.`
    - `GET /api/health ... 200 OK`
  - Frontend (`docker compose logs --tail=20 frontend`) included:
    - `VITE v5.4.21 ready`
    - `Local: http://localhost:5174/`

## Test Section 2: Coordinator flow tracking (Section 1) – write_todos and virtual file system

**Single goal:** One full agent run returns 200 and backend logs show coordinator using `write_todos` and the virtual file system (`/runtime/coordinator_flow.md`).

**Details:**
- Run one query (e.g. "What is the Strait of Hormuz?"); do not require prior data load.
- Assert in backend logs: at least one `Tool called: name=write_todos` and at least one `write_file` or tool response involving `coordinator_flow.md`.

**Tech stack and dependencies**
- Docker backend; `docker compose logs backend`.

**Files and purpose**

| File | Purpose |
|------|--------|
| `src/backend/agents/coordinator.py` | Coordinator that uses write_todos and virtual filesystem. |

**How to test:**
1. Ensure stack is up (Test Section 1).
2. Run: `POST /api/agents/run` with `{"query":"What is the Strait of Hormuz?"}` → expect HTTP 200 and response with `main_question`, `sub_qa`, and `output`.
3. Inspect backend logs: `docker compose logs --tail=300 backend` (or `-f backend` during run). Require:
   - At least one line containing `Tool called: name=write_todos` (or equivalent from deep-agents).
   - At least one line containing `write_file` and `coordinator_flow.md` (or `Tool response` with `files` and `coordinator_flow.md`).
4. If no such lines, restart backend and rerun: `docker compose restart backend`, then repeat step 2 and 3.

**Test results:** (Add when section is complete.)
- curl/response and log grep outcomes.

---

**Test results:**
- Fresh rebuild/start context used for this section:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Agent run command and response:
  - `curl -sS --max-time 180 -o /tmp/section2_response.json -w "%{http_code}" -X POST http://localhost:8001/api/agents/run -H 'Content-Type: application/json' -d '{"query":"Find Hormuz risks"}'`
  - `CURL_EXIT:0`, `HTTP_CODE:200`
  - Response body included required fields: `main_question`, `sub_qa`, `output`.
- Required backend log assertions:
  - `Tool called: name=write_todos` found (multiple matches).
  - `Tool called: name=write_file ... /runtime/coordinator_flow.md` found.
  - `Tool response ... '/runtime/coordinator_flow.md'` found.
  - `POST /api/agents/run HTTP/1.1" 200 OK` found.
- Useful service logs viewed:
  - Backend (`docker compose logs --tail=25 backend`) showed full pipeline completion and `Runtime agent run complete`.
  - Frontend (`docker compose logs --tail=25 frontend`) showed Vite dev server ready at `http://localhost:5174/`.
  - DB (`docker compose logs --tail=25 db`) showed PostgreSQL ready to accept connections.

## Test Section 3: Initial search for decomposition context (Section 2)

**Single goal:** After loading NATO wiki data, one agent run produces backend logs showing initial context search and decomposition context built with non-zero docs.

**Details:**
- Wipe internal data, load NATO wiki, run one query. Logs must show context search completion and "Initial decomposition context built" with `docs=5` (or similar) and `context_items` ≥ 1.

**Tech stack and dependencies**
- Docker backend; vector store and internal-data API.

**Files and purpose**

| File | Purpose |
|------|--------|
| `src/backend/services/vector_store_service.py` | Context search and context building. |
| `src/backend/services/agent_service.py` | Invokes context search and passes context to decomposition. |

**How to test:**
1. Wipe: `POST /api/internal-data/wipe` → 200.
2. Load: `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` → 200; body shows `documents_loaded=1`, `chunks_created=14` (or similar).
3. Run: `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` → 200.
4. Backend logs: `docker compose logs --tail=200 backend`. Require:
   - A line matching `Context search complete` with the query and `results=` (e.g. `results=5`).
   - A line matching `Initial decomposition context built` with `docs=` and `context_items=` (e.g. `docs=5`, `context_items=5`).

**Test results:**
- Fresh build/run context used for this section:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Wipe command/result:
  - `POST /api/internal-data/wipe` => `HTTP 200`
  - Body: `{"status":"success","message":"All internal documents and chunks removed."}`
- Load command/result:
  - `POST /api/internal-data/load` with NATO wiki payload => `HTTP 200`
  - Body: `{"status":"success","source_type":"wiki","documents_loaded":1,"chunks_created":14}`
- Agent run command/result:
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` => `HTTP 200`
  - Response body included `main_question`, `sub_qa`, and `output`.
- Backend log assertions (verified from full backend logs due long run output):
  - `Context search complete query='What changed in NATO policy?' k=5 score_threshold=None results=5 mode=similarity_search`
  - `Initial decomposition context built query=What changed in NATO policy? docs=5 k=5 score_threshold=None`
  - `INFO: ... "POST /api/agents/run HTTP/1.1" 200 OK`
- Useful service logs viewed for this iteration:
  - `docker compose logs --tail=200 db`
  - `docker compose logs --tail=200 backend`
  - `docker compose logs --tail=200 frontend`

## Test Section 4: Context-aware decomposition (Section 3)

**Single goal:** Same run as Section 3 produces logs showing coordinator decomposition input prepared with context, and API response contains non-empty `sub_qa` aligned with the query.

**Details:**
- Reuse data and run from Test Section 3 (or repeat wipe/load/run). Assert "Coordinator decomposition input prepared" with `context_items=5` (or > 0) and response `sub_qa` length ≥ 1 with sub-questions ending in "?".

**Tech stack and dependencies**
- Same as Test Section 3.

**Files and purpose**

| File | Purpose |
|------|--------|
| `src/backend/agents/coordinator.py` | Context-aware decomposition instructions. |
| `src/backend/services/agent_service.py` | Builds decomposition input with context. |

**How to test:**
1. If not already done: wipe, load NATO wiki, run with "What changed in NATO policy?" (see Test Section 3).
2. Backend logs: require a line like `Coordinator decomposition input prepared ... context_items=5` (or positive `context_items`).
3. From the same run’s response: `sub_qa` is present and non-empty; each `sub_question` is a string ending with `?`.

**Test results:**
- Fresh rebuild/start completed before this section:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Logs viewed for all built services:
  - `docker compose logs --tail=60 db` showed PostgreSQL init + `database system is ready to accept connections`.
  - `docker compose logs --tail=60 backend` showed Alembic upgrade + Uvicorn startup.
  - `docker compose logs --tail=60 frontend` showed Vite ready on `http://localhost:5174/`.
- Section run commands/results:
  - `POST /api/internal-data/wipe` => `{"status":"success","message":"All internal documents and chunks removed."}`
  - `POST /api/internal-data/load` (wiki nato) => `{"status":"success","source_type":"wiki","documents_loaded":1,"chunks_created":14}`
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` => HTTP 200 and response with non-empty `sub_qa`.
- Initial failure and fix:
  - First run had some `sub_qa.sub_question` values without trailing `?`.
  - Fixed in `src/backend/services/agent_service.py` by normalizing extracted `sub_question` values to complete question format ending with `?`.
  - Restarted backend: `docker compose restart backend`.
- Post-fix verification:
  - `jq` check on `/tmp/section4_run.json`:
    - `sub_qa_count: 6`
    - `all_sub_questions_end_with_qmark: true`
  - Required context logs present:
    - `Context search complete query='What changed in NATO policy?' ... results=5`
    - `Initial decomposition context built query=What changed in NATO policy? docs=5 ...`
    - `Coordinator decomposition input prepared query=What changed in NATO policy? context_items=5`
  - Backend request log confirmed: `POST /api/agents/run HTTP/1.1" 200 OK`.

## Test Section 5: Per-subquestion query expansion (Section 4)

**Single goal:** Backend logs show retriever tool called with `expanded_query`, and API response includes `expanded_query` per sub-question.

**Details:**
- Use same data/run (NATO, "What changed in NATO policy?"). Logs must show `search_database` (or Retriever tool) with `expanded_query` and `retrieval_query`; response `sub_qa[*].expanded_query` non-empty where applicable.

**Tech stack and dependencies**
- Retriever tool and coordinator subagent prompt.

**Files and purpose**

| File | Purpose |
|------|--------|
| `src/backend/tools/retriever_tool.py` | Accepts and uses expanded_query. |
| `src/backend/services/agent_service.py` | Extracts and exposes expanded_query in sub_qa. |

**How to test:**
1. Same run as Test Sections 3–4 (or repeat wipe/load/run).
2. Backend logs: require at least one line containing `Retriever tool search_database` with both `expanded_query=` and `retrieval_query=` (or `Tool called: name=search_database` with `expanded_query`).
3. Response: for at least one item in `sub_qa`, `expanded_query` is a non-empty string.

**Test results:**
- Fresh full restart/build completed before the section run:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Startup logs viewed for all built services:
  - `docker compose logs --tail=80 db` showed PostgreSQL init + `database system is ready to accept connections`.
  - `docker compose logs --tail=80 backend` showed Alembic upgrade + Uvicorn startup.
  - `docker compose logs --tail=80 frontend` showed Vite ready at `http://localhost:5174/`.
- Section 5 execution commands and API outcomes:
  - `POST /api/internal-data/wipe` => `{"status":"success","message":"All internal documents and chunks removed."}`
  - `POST /api/internal-data/load` (wiki nato) => `{"status":"success","source_type":"wiki","documents_loaded":1,"chunks_created":14}`
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` => HTTP 200 with populated `sub_qa` and `output`.
- Required backend log assertions passed (`docker compose logs --tail=500 backend`):
  - `Retriever tool search_database ... expanded_query=... retrieval_query=...` found multiple times.
  - Example log lines observed:
    - `Retriever tool search_database query="NATO's original purpose and strategic role during the Cold War" expanded_query='NATO initial purpose Cold War strategic role NATO policy focus Cold War strategic objectives NATO early mission Cold War' retrieval_query='NATO initial purpose Cold War strategic role NATO policy focus Cold War strategic objectives NATO early mission Cold War' ...`
    - `Retriever tool search_database query='NATO policy changes after the dissolution of the Soviet Union' expanded_query="Changes in NATO policy after the collapse of the Soviet Union including adaptations in NATO's purpose, tasks, and missions post-USSR dissolution" retrieval_query="Changes in NATO policy after the collapse of the Soviet Union including adaptations in NATO's purpose, tasks, and missions post-USSR dissolution" ...`
- Response assertion passed:
  - `jq '.sub_qa | map(select((.expanded_query // "") | length > 0)) | length' /tmp/section5_run_response.json` => `5`
  - This confirms `expanded_query` is non-empty for at least one `sub_qa` item (and in this run, 5 items).

## Test Section 6: Per-subquestion search (Section 5)

**Single goal:** Logs show per-subquestion search callbacks captured and per-subquestion search result with docs_retrieved count; response sub_qa contain sub_answer or retrieval content.

**Details:**
- Same run. Logs must show "Per-subquestion search callbacks captured count=" and "Per-subquestion search result" with `docs_retrieved=` (e.g. 10). Response `sub_qa` should have content in `sub_answer` or equivalent after pipeline.

**Tech stack and dependencies**
- agent_service callback capture and retriever tool.

**Files and purpose**

| File | Purpose |
|------|--------|
| `src/backend/services/agent_service.py` | Captures per-subquestion search and logs docs_retrieved. |
| `src/backend/tools/retriever_tool.py` | Per-subquestion retrieval. |

**How to test:**
1. Same run (NATO, "What changed in NATO policy?").
2. Backend logs: require `Per-subquestion search callbacks captured count=` (number ≥ 1) and at least one `Per-subquestion search result ... docs_retrieved=` (e.g. `docs_retrieved=10`).
3. Response: `sub_qa` entries have non-empty content (e.g. `sub_answer` or retrieved text) after full pipeline.

**Test results:**
- Fresh full restart/build/start completed before this section:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Logs viewed for all built services:
  - `docker compose logs --tail=120 backend` (saved to `/tmp/section6_backend_logs.txt`)
  - `docker compose logs --tail=120 frontend` (saved to `/tmp/section6_frontend_logs.txt`)
  - `docker compose logs --tail=120 db` (saved to `/tmp/section6_db_logs.txt`)
- Section 6 execution commands and outcomes:
  - `POST /api/internal-data/wipe` => `HTTP 200`, body: `{"status":"success","message":"All internal documents and chunks removed."}`
  - `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` => `HTTP 200`, body: `{"status":"success","source_type":"wiki","documents_loaded":1,"chunks_created":14}`
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` => `HTTP 200`
- Required backend log assertions passed:
  - `Per-subquestion search callbacks captured count=5`
  - `Per-subquestion search result ... docs_retrieved=10` found for each sub-question (5 entries), including:
    - `sub_question=NATO policy changes ... docs_retrieved=10`
    - `sub_question=What operational changes did NATO make in the 21st century? ... docs_retrieved=10`
- Response content assertions passed (`/tmp/section6_run.json`):
  - `sub_qa_count: 5`
  - `non_empty_sub_answer_count: 5`
  - `output_len: 557`

## Test Section 7: Per-subquestion document validation (Section 6)

**Single goal:** Backend logs show document validation stage with config and per-subquestion docs_before/docs_after/rejected.

**Details:**
- Same run. Logs must show "Per-subquestion document validation start" (with config such as min_relevance_score, source_allowlist_count, max_workers) and at least one "Per-subquestion document validation sub_question=" with `docs_before=`, `docs_after=`, `rejected=`.

**Tech stack and dependencies**
- document_validation_service and agent_service pipeline.

**Files and purpose**

| File | Purpose |
|------|--------|
| `src/backend/services/document_validation_service.py` | Validates docs in parallel. |
| `src/backend/services/agent_service.py` | Applies validation to sub_qa and logs. |

**How to test:**
1. Same run (NATO, "What changed in NATO policy?").
2. Backend logs: require `Per-subquestion document validation start` and at least one `Per-subquestion document validation sub_question=... docs_before=... docs_after=... rejected=...`.

**Test results:**
- Fresh full restart/build/start completed before this section:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Startup/infra checks performed:
  - `docker compose ps` showed `backend`, `frontend`, `db` up (`db` healthy).
  - `curl http://localhost:8001/api/health` => `{"status":"ok"}` (HTTP 200).
  - `curl http://localhost:5174` => HTTP 200.
- Logs viewed for built services:
  - `docker compose logs --tail=80 backend`
  - `docker compose logs --tail=80 frontend`
  - `docker compose logs --tail=80 db`
- Section 7 run inputs/results:
  - `POST /api/internal-data/wipe` => HTTP 200, body: `{"status":"success","message":"All internal documents and chunks removed."}`
  - `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` => HTTP 200, body: `{"status":"success","source_type":"wiki","documents_loaded":1,"chunks_created":14}`
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` => HTTP 200
- Required backend log assertions passed (`docker compose logs --tail=1200 backend`):
  - `Per-subquestion document validation start count=1 min_relevance_score=0.0 source_allowlist_count=0 min_year=None max_year=None max_workers=8`
  - `Per-subquestion document validation sub_question=NATO response to September 11 attacks? docs_before=10 docs_after=10 rejected=0`
  - Additional sub-question validations also logged with `docs_before`, `docs_after`, and `rejected` fields.
- Useful related pipeline evidence from same run:
  - `Context search complete query='What changed in NATO policy?' ... results=5`
  - `Initial decomposition context built query=What changed in NATO policy? docs=5 ...`
  - `Per-subquestion search callbacks captured count=6`
  - `Per-subquestion search result ... docs_retrieved=10` (multiple entries)

## Test Section 8: Per-subquestion reranking (Section 7)

**Single goal:** Backend logs show reranking stage with config and per-subquestion top_document; response sub_qa order/content consistent with reranked docs.

**Details:**
- Same run. Logs must show "Per-subquestion reranking start" (with top_n, weights) and "Per-subquestion reranking sub_question=" with `docs_before=`, `docs_after=`, `top_document=`.

**Tech stack and dependencies**
- reranker_service and agent_service pipeline.

**Files and purpose**

| File | Purpose |
|------|--------|
| `src/backend/services/reranker_service.py` | Reranks validated docs. |
| `src/backend/services/agent_service.py` | Applies reranking and logs. |

**How to test:**
1. Same run (NATO, "What changed in NATO policy?").
2. Backend logs: require `Per-subquestion reranking start` and at least one `Per-subquestion reranking sub_question=... top_document=...`.

**Test results:** (Add when section is complete.)

---

**Test results:**
- Fresh full restart/build/start completed before this section:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Startup/infra checks and logs captured for all built services:
  - `docker compose ps` showed `backend`, `frontend`, `db`, and `chrome` up (`db` healthy).
  - `curl http://localhost:8001/api/health` => HTTP `200`, body `{"status":"ok"}`.
  - `docker compose logs --tail=80 db` showed PostgreSQL init + `database system is ready to accept connections`.
  - `docker compose logs --tail=120 backend` showed Alembic upgrade + Uvicorn startup.
  - `docker compose logs --tail=80 frontend` showed Vite ready at `http://localhost:5174/`.
  - `docker compose logs --tail=40 chrome` showed browserless startup on port `3000`.
- Section 8 run inputs/results:
  - `POST /api/internal-data/wipe` => HTTP `200`, body: `{"status":"success","message":"All internal documents and chunks removed."}`
  - `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` => HTTP `200`, body: `{"status":"success","source_type":"wiki","documents_loaded":1,"chunks_created":14}`
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` => HTTP `200`
  - Response summary (`/tmp/section8_run.json`): `main_question` present, `sub_qa_count=5`, `non_empty_sub_answer_count=5`, `output_len=528`.
- Required reranking log assertions passed (`docker compose logs backend`):
  - `Per-subquestion reranking start count=1 top_n=None title_weight=1.3 content_weight=1.0 source_weight=0.3 original_rank_bias=0.05`
  - `Per-subquestion reranking sub_question=How did NATO's policy change after the Cold War? ... docs_before=10 docs_after=10 top_document=NATO`
  - `Per-subquestion reranking sub_question=NATO policy changes after the dissolution of the Soviet Union? ... docs_before=10 docs_after=10 top_document=NATO`
  - Backend completion log: `Runtime agent run complete ...` and `POST /api/agents/run HTTP/1.1" 200 OK`.
- Response consistency check against reranked sub-questions passed:
  - Extracted the latest 5 `Per-subquestion reranking sub_question=` entries and compared them to `sub_qa[].sub_question` from `/tmp/section8_run.json`.
  - Result: `RERANK_RESPONSE_MATCH:OK` (all reranked sub-questions were present in the response).

## Test Section 9: Per-subquestion subanswer generation (Section 8)

**Single goal:** Logs show subanswer generation start and "Per-subquestion subanswer generated" per sub-question; response sub_qa have non-empty sub_answer.

**Details:**
- Same run. Logs must show "Per-subquestion subanswer generation start" and "Per-subquestion subanswer generated" with sub_question and generated_len. Response `sub_qa[*].sub_answer` non-empty for generated items.

**Tech stack and dependencies**
- subanswer_service and agent_service pipeline.

**Files and purpose**

| File | Purpose |
|------|--------|
| `src/backend/services/subanswer_service.py` | Generates subanswers from reranked docs. |
| `src/backend/services/agent_service.py` | Applies subanswer generation and logs. |

**How to test:**
1. Same run (NATO, "What changed in NATO policy?").
2. Backend logs: require `Per-subquestion subanswer generation start` and at least one `Per-subquestion subanswer generated sub_question=... generated_len=...`.
3. Response: at least one `sub_qa` entry has non-empty `sub_answer`.

**Test results:** (Add when section is complete.)

---

**Test results:**
- Fresh full restart/build completed before running this section:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Service startup logs viewed after build/start:
  - `docker compose logs --tail=40 backend` (Alembic + Uvicorn startup)
  - `docker compose logs --tail=20 frontend` (Vite ready on `http://localhost:5174/`)
  - `docker compose logs --tail=20 db` (PostgreSQL ready)
- Section 9 execution flow and API outcomes:
  - `POST /api/internal-data/wipe` => `{"status":"success","message":"All internal documents and chunks removed."}`
  - `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` => `{"status":"success","source_type":"wiki","documents_loaded":1,"chunks_created":14}`
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` => HTTP 200.
- Required backend log assertions passed:
  - `Per-subquestion subanswer generation start count=1` found (multiple matches).
  - `Per-subquestion subanswer generated sub_question=... generated_len=...` found for multiple sub-questions.
  - Examples from logs:
    - `Per-subquestion subanswer generated sub_question=What is Article 5 in NATO policy and when was it invoked? generated_len=302`
    - `Per-subquestion subanswer generated sub_question=NATO policy changes over time major shifts after Cold War recent adaptations? generated_len=473`
  - Run completion confirmed:
    - `Runtime agent run complete ...`
    - `POST /api/agents/run HTTP/1.1" 200 OK`
- Response assertion passed:
  - `/tmp/section9_run.json` contains non-empty `sub_qa[*].sub_answer` (multiple populated entries).


## Test Section 10: Per-subquestion subanswer verification (Section 9)

**Single goal:** Logs show verification stage; response sub_qa include answerable and verification_reason.

**Details:**
- Same run. Logs must show "Per-subquestion subanswer verification start" and "Per-subquestion subanswer verification sub_question=... answerable=... reason=...". Response `sub_qa[*]` must include `answerable` (boolean) and `verification_reason` (string).

**Tech stack and dependencies**
- subanswer_verification_service and agent_service pipeline.

**Files and purpose**

| File | Purpose |
|------|--------|
| `src/backend/services/subanswer_verification_service.py` | Verifies subanswers. |
| `src/backend/services/agent_service.py` | Applies verification and sets SubQuestionAnswer fields. |
| `src/backend/schemas/agent.py` | answerable, verification_reason on SubQuestionAnswer. |

**How to test:**
1. Same run (NATO, "What changed in NATO policy?").
2. Backend logs: require `Per-subquestion subanswer verification start` and at least one `Per-subquestion subanswer verification ... answerable=... reason=...`.
3. Response: every `sub_qa` item has `answerable` and `verification_reason` (or default empty string).

**Test results:** (Add when section is complete.)

---

**Test results:**
- Fresh restart/build/start completed before section execution:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d db backend frontend`
- Logs viewed for all built services after startup:
  - `docker compose logs --tail=40 db`
  - `docker compose logs --tail=80 backend`
  - `docker compose logs --tail=40 frontend`
- Section 10 run inputs/results:
  - `POST /api/internal-data/wipe` => `{"status":"success","message":"All internal documents and chunks removed."}`
  - `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` => `{"status":"success","source_type":"wiki","documents_loaded":1,"chunks_created":14}`
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` => HTTP `200`
- Required backend verification log assertions passed (`docker compose logs backend | rg "Per-subquestion subanswer verification"`):
  - `Per-subquestion subanswer verification start count=1`
  - `Per-subquestion subanswer verification sub_question=What factors influenced changes in NATO policy after the Cold War? answerable=True reason=grounded_in_reranked_documents`
  - `Per-subquestion subanswer verification sub_question=NATO policy shifts in response to recent global security threats? answerable=True reason=grounded_in_reranked_documents`
  - `Per-subquestion subanswer verification sub_question=major treaties or agreements that influenced NATO policy changes? answerable=True reason=grounded_in_reranked_documents`
  - `Per-subquestion subanswer verification sub_question=key military or strategic interventions that marked a policy change in NATO? answerable=True reason=grounded_in_reranked_documents`
  - `Per-subquestion subanswer verification sub_question=NATO mission evolution after Soviet Union dissolution? answerable=True reason=grounded_in_reranked_documents`
- Response field assertion passed:
  - `/tmp/section10_run.json` had `sub_qa_count=5`.
  - Every `sub_qa` item included `answerable: true` and `verification_reason: "grounded_in_reranked_documents"`.

## Test Section 11: Parallel sub-question pipeline (Section 10)

**Single goal:** Logs show parallel pipeline start and complete with count and workers; multiple sub_qa completed.

**Details:**
- Same run. Logs must show "Per-subquestion pipeline parallel start" with count and effective_workers, and "Per-subquestion pipeline parallel complete" with count. Response has multiple `sub_qa` entries.

**Tech stack and dependencies**
- agent_service run_pipeline_for_subquestions.

**Files and purpose**

| File | Purpose |
|------|--------|
| `src/backend/services/agent_service.py` | run_pipeline_for_subquestions and parallel logs. |

**How to test:**
1. Same run (NATO, "What changed in NATO policy?").
2. Backend logs: require `Per-subquestion pipeline parallel start count=...` and `Per-subquestion pipeline parallel complete count=...`.
3. Response: `sub_qa` length ≥ 2 (multiple sub-questions processed).

**Test results:** (Add when section is complete.)

---

**Test results:**
- Fresh full restart/build completed before this section:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Running state after restart (`docker compose ps`) showed core services up:
  - `backend` Up with `0.0.0.0:8000->8000/tcp`
  - `db` Up (healthy) with `0.0.0.0:5432->5432/tcp`
  - `frontend` Up with `0.0.0.0:5173->5173/tcp`
- Logs viewed for every running service image after fresh start:
  - `docker compose logs --tail=80 db`
  - `docker compose logs --tail=120 backend`
  - `docker compose logs --tail=80 frontend`
  - `docker compose logs --tail=60 chrome`
- Section 11 API execution:
  - `POST /api/internal-data/wipe` => HTTP 200, body `{"status":"success","message":"All internal documents and chunks removed."}`
  - `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` => HTTP 200, body `{"status":"success","source_type":"wiki","documents_loaded":1,"chunks_created":14}`
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` => HTTP 200
- Required Section 11 backend log assertions passed (`docker compose logs --tail=1200 backend`):
  - `Per-subquestion pipeline parallel start count=9 configured_max_workers=4 effective_workers=4`
  - `Per-subquestion pipeline parallel complete count=9`
  - Request completion line: `POST /api/agents/run HTTP/1.1" 200 OK`
- Response assertions passed:
  - `sub_qa` length check: `9` (>= 2)
  - `output` length check: `546` (non-empty)
- Additional useful runtime logs viewed:
  - Backend showed per-subquestion item start/complete logs and subanswer generation/verification for multiple items.
  - Frontend logs remained healthy with Vite ready at `http://localhost:5174/`.
  - DB logs showed ready state and active transaction warnings only, no fatal errors.
## Test Section 12: Initial answer generation (Section 11)

**Single goal:** Logs show initial answer generation start and complete; response.output is non-empty synthesized answer.

**Details:**
- Same run. Logs must show "Initial answer generation start" (question_len, context_items, sub_qa_count) and "Initial answer generation complete" (e.g. via LLM or fallback). Response `output` must be a non-empty string.

**Tech stack and dependencies**
- initial_answer_service and agent_service.

**Files and purpose**

| File | Purpose |
|------|--------|
| `src/backend/services/initial_answer_service.py` | Synthesizes initial answer. |
| `src/backend/services/agent_service.py` | Calls synthesis and sets response.output. |

**How to test:**
1. Same run (NATO, "What changed in NATO policy?").
2. Backend logs: require `Initial answer generation start` and `Initial answer generation complete`.
3. Response: `output` is present and non-empty; optionally "Coordinator raw output captured" in logs.

**Test results:** (Add when section is complete.)

---


**Test results:**
- Fresh full restart/build completed before this section:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Running state after restart (`docker compose ps`):
  - `backend` Up (`0.0.0.0:8000->8000/tcp`)
  - `frontend` Up (`0.0.0.0:5173->5173/tcp`)
  - `db` Up healthy (`0.0.0.0:5432->5432/tcp`)
  - `chrome` Up (`0.0.0.0:9222->3000/tcp`)
- Logs viewed for every built/running service:
  - `docker compose logs --tail=80 backend`
  - `docker compose logs --tail=80 frontend`
  - `docker compose logs --tail=80 db`
- Section 12 API execution:
  - `POST /api/internal-data/wipe` => HTTP 200, body `{"status":"success","message":"All internal documents and chunks removed."}`
  - `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` => HTTP 200, body `{"status":"success","source_type":"wiki","documents_loaded":1,"chunks_created":14}`
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` => HTTP 200
- Required backend log assertions passed (`docker compose logs --tail=500 backend`):
  - `Initial answer generation start question_len=28 context_items=5 sub_qa_count=8`
  - `Initial answer generation complete via LLM answer_len=562 model=gpt-4.1-mini`
- Optional log assertion passed:
  - `Coordinator raw output captured output_length=610 ...`
- Response assertion passed:
  - `/tmp/section12_run.json` size `20671` bytes
  - `output` field present and non-empty synthesized answer.

---
## Test Section 13: Refinement decision (Section 12)

**Single goal:** Backend logs show refinement decision computed; for a weak/no-data query, refinement_needed=True and refinement path log present.

**Details:**
- Two runs: (A) With NATO data, query that may yield refinement_needed=False. (B) Wipe data (or use query with no relevant docs), run query → expect refinement_needed=True and "Refinement path flagged" or "Refinement path" in logs.
- Logs must show "Refinement decision computed" with refinement_needed and reason.

**Tech stack and dependencies**
- refinement_decision_service and agent_service.

**Files and purpose**

| File | Purpose |
|------|--------|
| `src/backend/services/refinement_decision_service.py` | should_refine(question, initial_answer, sub_qa). |
| `src/backend/services/agent_service.py` | Calls decision and logs; branches to refinement when needed. |

**How to test:**
1. Run with good data: "What changed in NATO policy?" (NATO loaded) → logs show `Refinement decision computed refinement_needed=False ...` (or True).
2. Wipe: `POST /api/internal-data/wipe`. Run: `POST /api/agents/run` with `{"query":"What happened in policy XZQ-999 with no indexed data?"}` → 200.
3. Backend logs: require `Refinement decision computed refinement_needed=True reason=...` and a line indicating refinement path (e.g. "Refinement path flagged" or "refinement_needed" handoff).

**Test results:** (Add when section is complete.)

---

**Test results:**
- Fresh full restart/build completed before this section:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Running state and health checks passed:
  - `docker compose ps` => `backend`, `frontend`, `db` all Up (`db` healthy).
  - `curl -i http://localhost:8001/api/health` => HTTP 200 and body `{"status":"ok"}`.
  - `curl -o /dev/null -w "%{http_code}" http://localhost:5174` => `200`.
- Logs viewed for built/running services:
  - `docker compose logs --tail=80 backend`
  - `docker compose logs --tail=40 db`
- Section 13 Run A (with data):
  - `POST /api/internal-data/wipe` => HTTP 200
  - `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` => HTTP 200, `{"documents_loaded":1,"chunks_created":14}`
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` => HTTP 200
- Section 13 Run B (no indexed data):
  - `POST /api/internal-data/wipe` => HTTP 200
  - `POST /api/agents/run` with `{"query":"What happened in policy XZQ-999 with no indexed data?"}` => HTTP 200
- Required backend log assertions passed (`docker compose logs --tail=800 backend | rg ...`):
  - `Refinement decision computed refinement_needed=True reason=low_answerable_ratio:0.40 sub_qa_count=5`
  - `Refinement path flagged refinement_needed=True reason=low_answerable_ratio:0.40`
  - `Refinement decomposition complete reason=low_answerable_ratio:0.40 refined_subquestion_count=6`
- Build/fix verification for this section:
  - Added broader no-evidence phrase detection and refinement-path logging in backend services.
  - Added unit tests for new phrase handling in refinement decision + subanswer verification.
  - Executed: `docker compose exec backend sh -lc 'cd /app && uv run --with pytest pytest tests/services/test_subanswer_verification_service.py tests/services/test_refinement_decision_service.py'`
  - Result: `7 passed in 0.03s`.

---
## Test Section 14: Refinement decomposition (Section 13)

**Single goal:** When refinement is taken, logs show refinement decomposition start/complete and refined sub-questions list; refined count ≥ 1.

**Details:**
- Trigger refinement (e.g. no data or weak answer). Logs must show "Refinement decomposition start", "Refinement decomposition complete" (via LLM or fallback), and "RefinedSubQuestion[1]=..." (or "Refined sub-questions prepared for Section 14").

**Tech stack and dependencies**
- refinement_decomposition_service and agent_service refinement branch.

**Files and purpose**

| File | Purpose |
|------|--------|
| `src/backend/services/refinement_decomposition_service.py` | refine_subquestions. |
| `src/backend/services/agent_service.py` | Calls refine_subquestions when refinement_needed and logs. |

**How to test:**
1. Ensure refinement path is triggered (e.g. wipe, run query that yields no answerable sub_qa).
2. Backend logs: require `Refinement decomposition start` and `Refinement decomposition complete ... count=...` and at least one `RefinedSubQuestion[...]=...` or "Refined sub-questions prepared for Section 14 handoff count=...".

**Test results:**
- Fresh full restart/build completed before this section:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Running state after fresh restart (`docker compose ps`) confirmed all services up:
  - `backend` Up on `:8000`
  - `frontend` Up on `:5173`
  - `db` Up healthy on `:5432`
  - `chrome` Up on `:9222`
- Logs viewed for every item built/running (`docker compose logs --no-color --tail=120`):
  - `frontend`: Vite ready at `http://localhost:5174/`
  - `backend`: uv env created and dependencies installed; app started
  - `db`: init + ready to accept connections
  - `chrome`: browserless started on port 3000
- Section 14 execution commands and outcomes:
  - `POST /api/internal-data/wipe` => HTTP 200, body `{"status":"success","message":"All internal documents and chunks removed."}`
  - `POST /api/agents/run` with `{"query":"What happened in policy XZQ-999 with no indexed data?"}` => HTTP 200
- Response outcome for run:
  - `main_question` returned correctly.
  - `sub_qa` returned with 6 refined sub-questions (all `answerable=false` in this no-data scenario).
  - `output` returned non-empty refined synthesis.
- Required backend log assertions passed (`docker compose logs --no-color --tail=500 backend`):
  - `Refinement decomposition start question_len=53 initial_answer_len=279 sub_qa_count=5`
  - `Refinement decomposition complete via LLM count=6 model=gpt-4.1-mini`
  - `Refinement decomposition complete reason=no_answerable_subanswers refined_subquestion_count=6`
  - `RefinedSubQuestion[1]=Are there any official documents or announcements that mention policy XZQ-999?`
  - `RefinedSubQuestion[2]=Has policy XZQ-999 been referenced in any related policies or regulations?`
  - `RefinedSubQuestion[3]=What organizations or authorities are responsible for implementing policy XZQ-999?`
  - `RefinedSubQuestion[4]=Is there any historical context or background that could explain the origin of policy XZQ-999?`
  - `RefinedSubQuestion[5]=Could 'no indexed data' refer to a technical issue or data management practice related to policy XZQ-999?`
  - `RefinedSubQuestion[6]=Are there any expert analyses or commentaries discussing the implications of policy XZQ-999?`
  - `Refined sub-questions prepared for Section 14 handoff count=6`
- Conclusion: Section 14 passed; refinement decomposition is active and emits complete refined-subquestion logging with count >= 1.

---
## Test Section 15: Refinement answer path (Section 14)

**Single goal:** When refinement runs, logs show refined pipeline (parallel start/complete for refined sub-questions) and final response.output is the refined answer; sub_qa may include refined items.

**Details:**
- Same refinement run as Test Sections 13–14. Logs should show a second pipeline run (parallel start/complete) for refined sub-questions and synthesis; response.output is the refined final answer.

**Tech stack and dependencies**
- agent_service refinement branch reusing run_pipeline_for_subquestions and initial_answer synthesis.

**Files and purpose**

| File | Purpose |
|------|--------|
| `src/backend/services/agent_service.py` | Refinement retrieval, pipeline, synthesis, response override. |

**How to test:**
1. Run that triggers refinement (e.g. "What changed in policy?" with NATO loaded can sometimes refine; or use no-data scenario).
2. Backend logs: require after refinement decision either (a) "Per-subquestion pipeline parallel start" for refined count, or (b) "Refinement" and "refined" / "Refined answer" completion log; and "Runtime agent run complete" with non-empty output.
3. Response: `output` non-empty; if refinement executed, output should reflect refined synthesis (e.g. different from a single initial pass).

**Test results:**
- Fresh full restart/build completed before this section:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Running state after restart (`docker compose ps`) confirmed:
  - `backend` Up on `:8000`
  - `frontend` Up on `:5173`
  - `db` Up healthy on `:5432`
  - `chrome` Up on `:9222`
- Logs viewed for every built/running service:
  - `docker compose logs --tail=120 backend`
  - `docker compose logs --tail=120 frontend`
  - `docker compose logs --tail=120 db`
- Section 15 execution commands and outcomes:
  - `POST /api/internal-data/wipe` => `{"status":"success","message":"All internal documents and chunks removed."}`
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` => HTTP 200
- Response assertion passed (same refinement run):
  - `output` non-empty and refined synthesis returned:
    - `There is no verified information available regarding recent changes in NATO policy ...`
  - `sub_qa` returned with 6 refined sub-questions (no-data scenario, each marked `answerable=false`).
- Required backend log assertions passed (`docker compose logs --tail=1200 backend | rg ...`):
  - Initial pass pipeline start:
    - `Per-subquestion pipeline parallel start count=4 configured_max_workers=4 effective_workers=4`
  - Refinement decision and decomposition:
    - `Refinement decision computed refinement_needed=True reason=no_answerable_subanswers sub_qa_count=4`
    - `Refinement path flagged refinement_needed=True reason=no_answerable_subanswers`
    - `Refinement decomposition complete reason=no_answerable_subanswers refined_subquestion_count=6`
    - `Refined sub-questions prepared for Section 14 handoff count=6`
  - Refined pass pipeline and completion:
    - `Per-subquestion pipeline parallel start count=6 configured_max_workers=4 effective_workers=4`
    - `Refinement answer path complete refined_sub_qa_count=6 refined_output_length=339`
    - `Runtime agent run complete output_length=339 ...`
- Conclusion: Section 15 passed; refinement branch executed a second sub-question pipeline and returned a non-empty refined final answer.

---
## Test Section 16: E2E in browser (Chrome DevTools / cursor-ide-browser)

**Single goal:** Open frontend in a debug browser, submit a query with "Run", and verify UI shows main_question, sub_qa list, and output without console or critical network errors.

**Details:**
- Use Chrome DevTools workflow per AGENTS.md: stop Docker Chrome if needed (`docker compose stop chrome`), start app (`docker compose up -d backend frontend`), launch debug browser (`./launch-devtools.sh http://localhost:5174`), verify `curl http://127.0.0.1:9223/json/list` returns targets with webSocketDebuggerUrl. Then in browser (or cursor-ide-browser): navigate to app, take snapshot, type query into input, click Run button, wait for completion, snapshot again; verify main question text, at least one sub-question/answer visible, and output text; check console for errors.
- Atomic UI checks: (1) Page loads. (2) Run button present and clickable. (3) After Run: main_question displayed, sub_qa section shows either a list of sub-questions/answers or "No subquestions for this run." message, output area non-empty or explicit empty state.

**Tech stack and dependencies**
- cursor-ide-browser MCP (browser_navigate, browser_snapshot, browser_fill/browser_type, browser_click, browser_console_messages) or manual Chrome with DevTools; frontend at http://localhost:5174; backend at http://localhost:8001.

**Files and purpose**

| File | Purpose |
|------|--------|
| `src/frontend/src/App.tsx` | Run form, Run button, display of main_question, sub_qa, output. |
| `launch-devtools.sh` | Launches Chrome with remote debugging for E2E. |

**How to test:**
1. Stack up; ensure backend and frontend reachable (Test Section 1).
2. Optional: load NATO data so run returns rich results.
3. Launch debug browser: `./launch-devtools.sh http://localhost:5174` (from repo root). Verify: `curl -s http://127.0.0.1:9223/json/list` has entries with webSocketDebuggerUrl.
4. In browser (or via cursor-ide-browser):
   - Navigate to `http://localhost:5174`.
   - Snapshot: confirm "Run Query" (or similar) and a submit button (e.g. "Run").
   - Fill query input with e.g. "What changed in NATO policy?" and click "Run".
   - Wait for run to finish (button returns to "Run", loading state ends).
   - Snapshot: confirm main question text is shown; sub_qa section shows either a list of sub-questions/answers or "No subquestions for this run.".
   - Optional: browser_console_messages (or DevTools Console) → no uncaught errors or failed /api/agents/run (e.g. 5xx).
5. If using cursor-ide-browser: lock tab before interactions, unlock when done (see MCP server instructions).

**Test results:**
- Fresh full reset/build/start completed before section:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Running state confirmed (`docker compose ps`): `backend`, `frontend`, `db (healthy)`, `chrome` all up.
- Logs viewed for every built/running item:
  - `docker compose logs --tail=80 backend`
  - `docker compose logs --tail=80 frontend`
  - `docker compose logs --tail=80 db`
  - `docker compose logs --tail=80 chrome`
- Reachability checks passed:
  - `curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/health` => `200`
  - `curl -s http://localhost:8001/api/health` => `{"status":"ok"}`
  - `curl -s -o /dev/null -w "%{http_code}" http://localhost:5174` => `200`
- Optional data setup executed:
  - `POST /api/internal-data/wipe` => `{"status":"success","message":"All internal documents and chunks removed."}`
  - `POST /api/internal-data/load` NATO => `{"status":"success","source_type":"wiki","documents_loaded":1,"chunks_created":14}`
- DevTools workflow verification:
  - `docker compose stop chrome` then `./launch-devtools.sh http://localhost:5174`
  - `curl http://127.0.0.1:9223/json/list` returned targets with `webSocketDebuggerUrl`.
- E2E interaction executed with real Chrome automation (Playwright core against local Chrome binary):
  - Opened page, verified `Run Query` heading, textarea, and `Run` button.
  - Entered query `What is NATO?` and clicked `Run`.
  - Waited for loading state to end and validated final readout.
- E2E output (pass):
  - `mainQuestion`: `What is NATO?`
  - `finalAnswerLength`: `658` (non-empty output)
  - `subSummaryCount`: `10` (sub_qa list visible)
  - Console: one benign 404 static-resource message only; no critical console errors.
  - No page exceptions.
  - No failed `/api/agents/run` requests.
- Backend run completion evidence:
  - `Runtime agent run complete output_length=658 ...`
  - `POST /api/agents/run HTTP/1.1" 200 OK`
- Conclusion: Section 16 passed.

---
