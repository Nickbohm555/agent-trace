# Agent-Search Test Plan (Real / E2E)

Atomic testing sections to verify each implemented part via **docker logs** and **Chrome DevTools** (cursor-ide-browser). Run sections **sequentially**. Not mock tests—real runs and real log/UI checks.

**Reference:** AGENTS.md for docker commands, health URL, wipe/load/run APIs, and browser debug workflow (`./launch-devtools.sh http://localhost:5174`, DevTools at `http://127.0.0.1:9223/json/list`).


Current section to work on: 17
---

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

**Test results:** (Add when section is complete.)
- Commands and outcomes.

---

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

**Test results:** (Add when section is complete.)

---

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

**Test results:** (Add when section is complete.)

---

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

**Test results:** (Add when section is complete.)

---

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

**Test results:** (Add when section is complete.)

---

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

**Test results:** (Add when section is complete.)

---

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

**Test results:** (Add when section is complete.)

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

**Test results:** (Add when section is complete.)

---

## Test Section 16: E2E in browser (Chrome DevTools / cursor-ide-browser)

**Single goal:** Open frontend in a debug browser, submit a query with "Run", and verify UI shows main_question, sub_qa list, and output without console or critical network errors.

**Details:**
- Use Chrome DevTools workflow per AGENTS.md: stop Docker Chrome if needed (`docker compose stop chrome`), start app (`docker compose up -d backend frontend`), launch debug browser (`./launch-devtools.sh http://localhost:5174`), verify `curl http://127.0.0.1:9223/json/list` returns targets with webSocketDebuggerUrl. Then in browser (or cursor-ide-browser): navigate to app, take snapshot, type query into input, click Run button, wait for completion, snapshot again; verify main question text, at least one sub-question/answer visible, and output text; check console for errors.
- Atomic UI checks: (1) Page loads. (2) Run button present and clickable. (3) After Run: main_question displayed, sub_qa list or "No subquestions" message, output area non-empty or explicit empty state.

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
   - Snapshot: confirm main question text is shown; sub_qa section shows either a list of sub-questions/answers or "No subquestions for this run."; output area shows synthesized answer or placeholder.
   - Optional: browser_console_messages (or DevTools Console) → no uncaught errors or failed /api/agents/run (e.g. 5xx).
5. If using cursor-ide-browser: lock tab before interactions, unlock when done (see MCP server instructions).

**Test results:** (Add when section is complete.)
- Snapshot summaries and console/network outcomes.

---
