## Section 1: Coordinator flow tracking via write_todos and virtual file system

**Single goal:** The coordinator agent uses the deep-agents (LangGraph) `write_todos` planning tool and the **deep-agents virtual file system** to keep track of the pipeline flow so it does not lose context across steps.

### Implemented
- Updated `src/backend/agents/coordinator.py` to explicitly configure deep-agents backend as `StateBackend` (virtual filesystem backend) when creating the coordinator agent.
- Strengthened coordinator system prompt to require:
  - `write_todos` at run start and throughout stage transitions.
  - `read_file`/`write_file` usage on `/runtime/coordinator_flow.md` for persisted flow tracking across steps.
  - Stage-aligned planning for the full initial + refinement pipeline.
- Added coordinator creation logging to include backend and flow tracking file path for visibility.
- Added/updated tests in `src/backend/tests/agents/test_coordinator_agent.py`:
  - Verifies coordinator prompt contains mandatory `write_todos` + virtual filesystem instructions.
  - Verifies backend passed to deep-agents is `StateBackend`.
  - Verifies backend override wiring works.

### Validation and logs
- Fresh restart (full rebuild):
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Backend unit tests:
  - `docker compose exec backend sh -lc 'uv run pytest tests/agents/test_coordinator_agent.py tests/services/test_agent_service.py'`
  - Result: `5 passed`
- API smoke selection command:
  - `docker compose exec backend sh -lc 'uv run pytest tests/api -m smoke'`
  - Result: `2 deselected` (no smoke-selected tests)
- Integration run:
  - `POST /api/agents/run` with `{"query":"What is the Strait of Hormuz?"}`
  - Result: `HTTP 200`
  - Response included `main_question`, `sub_qa`, and `output`.
- Backend logs confirmed required runtime behavior:
  - `Tool called: name=write_todos ...`
  - `Tool called: name=write_file input={'file_path': '/runtime/coordinator_flow.md', ...}`
  - `Tool response ... Command(update={'files': {'/runtime/coordinator_flow.md': ...}})`
  - Additional flow updates and staged todo status transitions were present.
- Container log sweep performed (`backend`, `frontend`, `db`) and `docker compose ps` checked all services up/healthy.

### Noted runtime detail
- `GET /api/health` currently returns `404 Not Found` in this codebase state.

## Section 2: Initial search for decomposition context

**Single goal:** Run one retrieval for the user question and pass top-k results as context into decomposition.

**Details:**
- One retrieval (same vector store/retriever as sub-question search) using the raw user question, before decomposition.
- Return bounded top-k docs/snippets; pass as structured context (e.g. list of doc IDs, snippets, or metadata) into decomposition. Do not change decomposition logic; only add the search step and wire its output.
- k and retriever config (e.g. score threshold) configurable (env or settings).

**Tech:** Existing retriever/vector_store_service. No new packages. No Docker change unless new env vars.

**Files**

| File | Purpose |
|------|--------|
| `src/backend/services/agent_service.py` | Invoke initial search before coordinator/decomposition; pass context into decomposition. |
| `src/backend/services/vector_store_service.py` (or equivalent) | Use existing similarity search; optional thin wrapper for context-only search with configurable k. |
| `src/backend/schemas/agent.py` (optional) | Optional schema for “initial search context” if not inlined in run request/state. |

**How to test:** Unit: mock retriever → assert returned context is passed to decomposition. Integration: full agent request → decomposition receives non-empty context when store has relevant docs.

### Implemented
- Added `search_documents_for_context(...)` in `src/backend/services/vector_store_service.py` to run one pre-decomposition retrieval with configurable `k` and optional `score_threshold`.
- Added `build_initial_search_context(...)` in `src/backend/services/vector_store_service.py` to shape context into bounded structured items (`rank`, `document_id`, `title`, `source`, `snippet`).
- Updated `src/backend/services/agent_service.py` to:
  - Run one initial context retrieval before coordinator invocation.
  - Build structured context and inject it into the coordinator’s first `HumanMessage` as decomposition context.
  - Add new runtime logs for visibility of retrieval mode, result count, and context build metadata.
- Added unit coverage in:
  - `src/backend/tests/services/test_agent_service.py` to assert context retrieval/build is called and coordinator receives context in input message.
  - `src/backend/tests/services/test_vector_store_service.py` to validate new context-search wrapper behavior and context shape formatting.

### Validation and logs
- Fresh environment reset before implementation:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Backend restarted after code changes:
  - `docker compose restart backend`
- Unit tests:
  - `docker compose exec backend sh -lc 'uv pip install pytest && uv run pytest tests/services/test_agent_service.py tests/services/test_vector_store_service.py'`
  - Result: `7 passed`
- Integration flow:
  - `POST /api/internal-data/wipe` -> success
  - `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` -> `documents_loaded=1`, `chunks_created=14`
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` -> `HTTP 200`
- Backend logs confirmed the Section 2 behavior:
  - `Context search complete query='What changed in NATO policy?' k=5 score_threshold=None results=5 mode=similarity_search`
  - `Initial decomposition context built query=What changed in NATO policy? docs=5 k=5 score_threshold=None`
  - `INFO ... "POST /api/agents/run HTTP/1.1" 200 OK`
- Container log sweep completed after implementation:
  - `docker compose logs --tail=60 backend`
  - `docker compose logs --tail=60 frontend`
  - `docker compose logs --tail=60 db`
  - `docker compose ps` (all services up; db healthy)

**Test results:** Complete.

## Section 4: Per-subquestion query expansion

**Single goal:** For each sub-question, produce an expanded query (synonyms, reformulations) for retrieval.

**Details:**
- Input: one sub-question. Output: one expanded query (or small set; if multiple, downstream defines combination, e.g. union). Expansion = LLM or rule/keyword-based. No retrieval or reranking changes here.

**Tech:** LLM if used; no new packages. No Docker change.

**Files**

| File | Purpose |
|------|--------|
| `src/backend/services/agent_service.py` or new `src/backend/services/query_expansion_service.py` | sub_question → expanded_query; call from per-subquestion pipeline. |
| `src/backend/schemas/agent.py` (optional) | Optional expanded_query on SubQuestionAnswer or pipeline state for observability. |

**How to test:** Unit: sub-question → expanded query non-empty (or equals original if no-op). Integration: one sub-question through pipeline → search uses expanded query.

### Implemented
- Updated `src/backend/agents/coordinator.py` subagent prompt so each delegated sub-question must produce one `expanded_query` and call the retriever with both `query` and `expanded_query`.
- Updated `src/backend/tools/retriever_tool.py`:
  - Added optional `expanded_query` argument to `search_database`.
  - Retrieval now uses `expanded_query` when present, falling back to `query` when absent.
  - Added detailed retrieval logs: `query`, `expanded_query`, and effective `retrieval_query`.
- Updated `src/backend/schemas/agent.py`:
  - Added `expanded_query: str = ""` to `SubQuestionAnswer` for visibility.
- Updated `src/backend/services/agent_service.py`:
  - Added parser to extract `expanded_query` from tool-call input payload.
  - Wired extracted value into `SubQuestionAnswer` construction paths.
  - Extended run-end summary logs to include `expanded_query` per sub-question.
- Added/updated tests:
  - `src/backend/tests/tools/test_retriever_tool.py`: verifies expanded query is used as retrieval query.
  - `src/backend/tests/agents/test_coordinator_agent.py`: verifies prompt requires `query` + `expanded_query` tool inputs.
  - `src/backend/tests/services/test_agent_service.py`: verifies `expanded_query` extraction and response population.

### Validation and logs
- Full fresh restart before edits:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Backend restarted after code changes:
  - `docker compose restart backend`
- Unit tests:
  - `docker compose exec backend sh -lc 'uv pip install pytest && uv run pytest tests/tools/test_retriever_tool.py tests/agents/test_coordinator_agent.py tests/services/test_agent_service.py'`
  - Result: `9 passed`
- Integration data prep:
  - `POST /api/internal-data/wipe` -> `200`
  - `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` -> `200`, `documents_loaded=1`, `chunks_created=14`
- Integration run:
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` -> `200`
  - Response included `sub_qa[*].expanded_query` populated per sub-question.
- Backend log evidence (expanded-query path active):
  - `Tool called: name=search_database input={'query': ..., 'expanded_query': ...}`
  - `Retriever tool search_database query='...' expanded_query='...' retrieval_query='...' limit=10 filter=None result_count=10`
  - `Extracted sub_qa from callback sub_question=... expanded_query=...`
  - `SubQuestionAnswer[1] sub_question=... expanded_query=...`
  - `Runtime agent run complete output_length=1518 ...`
- Container checks and log sweep:
  - `docker compose ps` -> all services up (`db` healthy)
  - `docker compose logs --tail=220 backend`
  - `docker compose logs --tail=120 frontend`
  - `docker compose logs --tail=120 db`

**Test results:** Complete.

## Section 3: Question decomposition informed by context

**Single goal:** Produce narrow sub-questions from the user question using initial-search context (Section 2).

**Details:**
- Input: initial-search context + user question. Output: list of sub-questions (one concept per sub-question, complete questions ending with “?”).
- Decomposition = LLM (coordinator prompt) or dedicated function; deliverable = context-aware sub-questions only. No query expansion, reranking, or refinement here.

**Tech:** Existing LLM and coordinator. No new packages. No Docker change.

**Files**

| File | Purpose |
|------|--------|
| `src/backend/agents/coordinator.py` | Update system prompt/inputs so coordinator gets initial-search context and uses it for sub-questions. |
| `src/backend/services/agent_service.py` | Pass initial-search context (Section 2) into coordinator (e.g. first HumanMessage or dedicated context field). |

**How to test:** Unit: fixed context + user question → decomposition returns list of strings, each ending with “?”. Integration: ambiguous question → sub-questions align with provided context.

### Implemented
- Strengthened coordinator decomposition instructions in `src/backend/agents/coordinator.py`:
  - Explicitly treat `Initial retrieval context for decomposition` in the user message as grounding input.
  - Require narrow, context-aware sub-questions with one concept per question.
  - Require `task()` delegation to preserve question form (`?` suffix) and keep decomposition stage mandatory.
  - Added flow-file update guardrail to prefer `read_file + edit_file` after initial file creation for clearer tool behavior.
- Updated coordinator input construction in `src/backend/services/agent_service.py`:
  - Always sends a structured decomposition payload (`User question` + serialized initial context, even when empty).
  - Includes explicit decomposition constraints in the runtime message.
  - Added runtime logging: `Coordinator decomposition input prepared ...`.
- Added/updated unit tests:
  - `src/backend/tests/agents/test_coordinator_agent.py` checks prompt contract for context-aware decomposition and delegation constraints.
  - `src/backend/tests/services/test_agent_service.py` checks coordinator input payload constraints and empty-context behavior.

### Validation and logs
- Full fresh restart before implementation:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Backend restart after code changes:
  - `docker compose restart backend`
- Unit tests:
  - `docker compose exec backend sh -lc 'uv pip install pytest && uv run pytest tests/agents/test_coordinator_agent.py tests/services/test_agent_service.py'`
  - Result: `6 passed`
- Integration data prep:
  - `POST /api/internal-data/wipe` -> `200`
  - `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` -> `200`, `documents_loaded=1`, `chunks_created=14`
- Integration run:
  - `POST /api/agents/run` with `{"query":"What changed in policy?"}` -> `200`
  - Response included decomposition-driven NATO-focused sub-question pipeline and final synthesized output.
- Backend log excerpts:
  - `Runtime agent run start query=What changed in policy? query_length=23`
  - `Initial decomposition context built query=What changed in policy? docs=5 k=5 score_threshold=None`
  - `Coordinator decomposition input prepared query=What changed in policy? context_items=5`
  - `Runtime agent run complete output_length=2042 ...`
- Container checks/logs:
  - `docker compose ps` -> all services up, `db` healthy.
  - `docker compose logs --tail=80 frontend`
  - `docker compose logs --tail=80 db`

**Test results:** Complete.

## Section 5: Per-subquestion search

**Single goal:** Run retrieval per sub-question using the expanded query (Section 4); return ranked list of documents per sub-question.

**Details:**
- Input: expanded query (or sub-question if expansion skipped). Output: ordered list of docs (or IDs + snippets) per sub-question. Use existing vector store/retriever; pipeline must call it with expanded query when expansion enabled. No validation, reranking, or subanswer generation here.

**Tech:** Existing retriever and vector_store_service. No new packages. No Docker change.

**Files**

| File | Purpose |
|------|--------|
| `src/backend/services/agent_service.py` or pipeline module | Per sub-question: call expansion then retriever with expanded query; store retrieved docs per sub-question. |
| `src/backend/tools/retriever_tool.py` | Invoked as-is or via service wrapper (query string → docs). |

**How to test:** Unit: mock retriever + expanded query → returned doc list passed to next step. Integration: one sub-question through expansion + search → doc count and content as expected.

### Implemented
- Updated `src/backend/services/agent_service.py` to add explicit per-subquestion search observability:
  - Added `_estimate_retrieved_doc_count(...)` to count ranked retrieval rows in retriever output.
  - Added run-level log after callback capture: `Per-subquestion search callbacks captured count=...`.
  - Added per-item log in callback extraction path: `Per-subquestion search result ... docs_retrieved=...` including sub-question and expanded query.
- Added unit coverage in `src/backend/tests/services/test_agent_service.py`:
  - `test_extract_sub_qa_uses_callback_captured_search_calls` validates callback-captured per-subquestion doc list is passed through into `SubQuestionAnswer.sub_answer` and preserves `expanded_query`.
  - `test_estimate_retrieved_doc_count_counts_ranked_lines` validates ranked-doc counting logic used by logs.
- Reused existing `src/backend/tools/retriever_tool.py` behavior that already executes search using `expanded_query` when provided and logs `retrieval_query`/`result_count`.

### Validation and logs
- Full fresh restart before implementation:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Backend restart after code changes:
  - `docker compose restart backend`
- Unit tests:
  - `docker compose exec backend sh -lc 'uv pip install pytest && uv run pytest tests/tools/test_retriever_tool.py tests/services/test_agent_service.py'`
  - Result: `9 passed`
- Integration data prep:
  - `POST /api/internal-data/wipe` -> `200`
  - `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` -> `200`, `documents_loaded=1`, `chunks_created=14`
- Integration run:
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` -> `200`
  - Response included ranked per-subquestion retrieval output in `sub_qa[*].sub_answer` and populated `sub_qa[*].expanded_query`.
- Backend log evidence for Section 5:
  - `Retriever tool search_database query='...' expanded_query='...' retrieval_query='...' limit=10 ... result_count=10`
  - `Per-subquestion search callbacks captured count=18`
  - `Per-subquestion search result sub_question=... expanded_query=... docs_retrieved=10 ...`
- Container checks/logs:
  - `docker compose ps` -> all services up; `db` healthy.
  - `docker compose logs --tail=220 backend`
  - `docker compose logs --tail=120 frontend`
  - `docker compose logs --tail=120 db`

**Test results:** Complete.

## Section 6: Per-subquestion document validation (parallel)

**Single goal:** Validate retrieved documents per sub-question (relevance/constraints); run validations in parallel across documents.

**Details:**
- Input: per-subquestion doc list. Output: per-subquestion list of docs that passed (or validation flags). Criteria configurable (score threshold, date, source allowlist); parallel within sub-question (thread pool or async). No reranking or subanswer generation here.

**Tech:** LLM or rule-based; add any new dependency to pyproject.toml. No Docker change unless new env vars.

**Files**

| File | Purpose |
|------|--------|
| New `src/backend/services/document_validation_service.py` (or equivalent) | Validate list of docs in parallel; expose to pipeline. |
| `src/backend/services/agent_service.py` or pipeline module | After search, call validation per sub-question; pass validated docs to reranking. |

**How to test:** Unit: fixed docs + rules → validated output subset/flags correct; parallel (mock delay, check total time). Integration: search → validation → only valid docs proceed.

### Implemented
- Added `src/backend/services/document_validation_service.py`:
  - Parses retriever output rows into structured documents.
  - Applies configurable validation constraints: relevance threshold (`DOCUMENT_VALIDATION_MIN_RELEVANCE_SCORE`), source allowlist (`DOCUMENT_VALIDATION_SOURCE_ALLOWLIST`), and date window (`DOCUMENT_VALIDATION_MIN_YEAR` / `DOCUMENT_VALIDATION_MAX_YEAR`, optional strict year presence).
  - Runs per-document validation in parallel via `ThreadPoolExecutor` with configurable workers (`DOCUMENT_VALIDATION_MAX_WORKERS`).
  - Returns structured validation results and provides formatter for validated document output.
- Updated `src/backend/services/agent_service.py`:
  - Added `_apply_document_validation_to_sub_qa(...)` after per-subquestion search extraction.
  - Applies validation per sub-question and rewrites `sub_answer` to validated document rows when parseable retrieval rows are present.
  - Preserves original `sub_answer` when no parseable rows are found.
  - Added runtime logs for validation config and per-subquestion before/after/rejected counts.
- Added tests:
  - `src/backend/tests/services/test_document_validation_service.py`
    - Validates rule-based filtering (relevance/source/year).
    - Verifies parallel execution via timing with mocked per-document delay.
  - `src/backend/tests/services/test_agent_service.py`
    - Verifies runtime sub_qa validation step is invoked and filtered document output is applied.

### Validation and logs
- Full fresh rebuild/restart before implementation:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Backend tests:
  - `docker compose exec backend sh -lc 'uv pip install pytest && uv run pytest tests/services/test_document_validation_service.py tests/services/test_agent_service.py'`
  - Result: `9 passed`
- Smoke selector command:
  - `docker compose exec backend sh -lc 'uv run pytest tests/api -m smoke'`
  - Result: `2 deselected` (no smoke-selected tests)
- Integration run:
  - `POST /api/internal-data/wipe` -> `200`
  - `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` -> `documents_loaded=1`, `chunks_created=14`
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` -> `200`
- Backend log evidence:
  - `Per-subquestion search callbacks captured count=7`
  - `Per-subquestion document validation start count=7 min_relevance_score=0.0 source_allowlist_count=0 min_year=None max_year=None max_workers=8`
  - `Per-subquestion document validation sub_question=... docs_before=10 docs_after=10 rejected=0`
  - `Runtime agent run complete output_length=1011 ...`
- Changed container restart after implementation:
  - `docker compose restart backend`
  - `docker compose ps` confirmed `backend`, `frontend`, `db` up (`db` healthy)
- Post-change log sweep:
  - `docker compose logs --tail=120 backend`
  - `docker compose logs --tail=80 frontend`
  - `docker compose logs --tail=80 db`

## Section 7: Per-subquestion reranking

**Single goal:** Rerank validated documents per sub-question so top results are best for subanswer generation.

**Details:**
- Input: per-subquestion validated doc list. Output: same docs in new order (or top-n) per sub-question. Reranker = cross-encoder, LLM, or heuristic. No subanswer generation or verification here.

**Tech:** Add reranker dependency if needed (e.g. sentence-transformers, LLM) in pyproject.toml. No Docker change unless new runtime dependency.

**Files**

| File | Purpose |
|------|--------|
| New `src/backend/services/reranker_service.py` (or equivalent) | rerank(docs, query) → ordered list; cross-encoder or LLM. |
| `src/backend/services/agent_service.py` or pipeline module | After validation, call reranker per sub-question; pass reranked docs to subanswer generation. |

**How to test:** Unit: fixed docs + query → output order differs when non-trivial; top doc sensible. Integration: validation → rerank → order and count verified.

### Implemented
- Added `src/backend/services/reranker_service.py`:
  - `RerankerConfig` and `build_reranker_config_from_env()` with optional `RERANK_TOP_N` and weight settings.
  - Heuristic lexical reranker (`rerank_documents`) that scores per-query overlap across title/content/source plus a small original-rank bias.
  - Returns reranked documents with rank reset to the new order.
- Updated `src/backend/services/agent_service.py`:
  - Added `_RERANKER_CONFIG` initialization.
  - Added `_apply_reranking_to_sub_qa(...)` immediately after document validation.
  - Reranks parsed validated docs per sub-question using `expanded_query` fallback to `sub_question`.
  - Added visibility logs for reranker config and per-subquestion before/after counts + top document.
- Added tests:
  - `src/backend/tests/services/test_reranker_service.py`
    - Validates non-trivial rerank ordering and `top_n` behavior.
  - `src/backend/tests/services/test_agent_service.py`
    - Added reranking pipeline test to verify per-subquestion reordered output.
- Operational fix discovered while validating logs:
  - Added `/api/health` endpoint in `src/backend/main.py` to match AGENTS.md runbook.
  - Added `src/backend/tests/api/test_health.py`.

### Validation and logs
- Full fresh restart before implementation:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Backend restart after changes:
  - `docker compose restart backend`
- Unit tests:
  - `docker compose exec backend sh -lc 'uv pip install pytest && uv run pytest tests/services/test_reranker_service.py tests/services/test_agent_service.py tests/api/test_health.py'`
  - Result: `11 passed`
- Integration data prep + run:
  - `POST /api/health` -> `200`, `{"status":"ok"}`
  - `POST /api/internal-data/wipe` -> `200`
  - `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` -> `200`, `documents_loaded=1`, `chunks_created=14`
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` -> `200`
- Backend log evidence:
  - `Per-subquestion document validation start count=10 ...`
  - `Per-subquestion reranking start count=10 top_n=None title_weight=1.3 content_weight=1.0 source_weight=0.3 original_rank_bias=0.05`
  - `Per-subquestion reranking sub_question=... docs_before=10 docs_after=10 top_document=NATO`
  - `Runtime agent run complete output_length=1579 ...`
- Container/log checks:
  - `docker compose ps` -> all services up, `db` healthy.
  - `docker compose logs --tail=240 backend`
  - `docker compose logs --tail=120 frontend`
  - `docker compose logs --tail=120 db`

**Test results:** Complete.

## Section 8: Per-subquestion subanswer generation

**Single goal:** Generate sub-answer text per sub-question from the reranked document set (Section 7).

**Details:**
- Input: sub-question + reranked docs for that sub-question. Output: one sub-answer string per sub-question. Use LLM (or existing subagent) with reranked docs as context; concise, attributed. No verification here.

**Tech:** Existing LLM and prompts. No new packages. No Docker change.

**Files**

| File | Purpose |
|------|--------|
| `src/backend/services/agent_service.py` or new `src/backend/services/subanswer_service.py` | (sub_question, reranked_docs) → sub_answer; use Section 7 output. |
| `src/backend/agents/coordinator.py` (optional) | If RAG subagent does subanswer, ensure it receives reranked docs; else keep in dedicated service. |

**How to test:** Unit: sub-question + fixed reranked docs → sub-answer non-empty and on-topic. Integration: rerank → subanswer → SubQuestionAnswer.sub_answer set.

### Implemented
- Added new `src/backend/services/subanswer_service.py`:
  - `generate_subanswer(sub_question, reranked_retrieved_output)` generates concise attributed subanswers from reranked evidence.
  - Uses `ChatOpenAI` with existing model stack when available.
  - Added deterministic fallback path (top reranked evidence sentence + source) and explicit no-doc fallback.
  - Added guardrail logging and fallback when `OPENAI_API_KEY` is missing.
- Updated `src/backend/services/agent_service.py`:
  - Added `_apply_subanswer_generation_to_sub_qa(...)` stage.
  - Wired pipeline order to: extraction -> validation -> reranking -> subanswer generation.
  - Added section visibility logs:
    - `Per-subquestion subanswer generation start ...`
    - `Per-subquestion subanswer generated ...`
- Added/updated tests:
  - New `src/backend/tests/services/test_subanswer_service.py` for fallback and LLM success behavior.
  - Updated `src/backend/tests/services/test_agent_service.py` to assert subanswer generation is invoked and written to `SubQuestionAnswer.sub_answer`.

### Validation and logs
- Full reboot before implementation:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Container refresh after edits:
  - `docker compose restart backend`
- Unit tests:
  - `docker compose exec backend sh -lc 'uv pip install pytest && uv run pytest tests/services/test_subanswer_service.py tests/services/test_agent_service.py'`
  - Result: `11 passed`
- Smoke selector command:
  - `docker compose exec backend sh -lc 'uv run pytest tests/api -m smoke'`
  - Result: `3 deselected` (no smoke-selected tests)
- Integration data prep:
  - `POST /api/internal-data/wipe` -> `200`
  - `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` -> `documents_loaded=1`, `chunks_created=14`
- Integration run:
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` -> `200`
  - Response contained populated `sub_qa[*].sub_answer` values generated from reranked evidence.
- Backend log evidence:
  - `Per-subquestion reranking start count=5 ...`
  - `Per-subquestion subanswer generation start count=5`
  - `Per-subquestion subanswer generated sub_question=... generated_len=...`
  - `SubQuestionAnswer summary count=5`
  - `Runtime agent run complete output_length=1434 ...`
- Container state and log checks:
  - `docker compose ps` -> backend/frontend/chrome up, db healthy.
  - `docker compose logs --tail=220 backend`
  - `docker compose logs --tail=80 frontend`
  - `docker compose logs --tail=80 db`

## Section 9: Per-subquestion subanswer verification

**Single goal:** Verify each sub-answer (against reranked docs or criteria); expose answerable vs not (or confidence) for refinement.

**Details:**
- Input: sub-question, sub-answer, docs for that sub-question. Output: verification per sub-question (e.g. boolean answerable or score, optional short reason). LLM or rule-based. Expose in pipeline state or SubQuestionAnswer. No refinement logic here.

**Tech:** LLM if used. No new packages. No Docker change.

**Files**

| File | Purpose |
|------|--------|
| `src/backend/schemas/agent.py` | Optional verification fields on SubQuestionAnswer (e.g. answerable: bool, verification_reason: str). |
| New `src/backend/services/subanswer_verification_service.py` or equivalent | verify(sub_question, sub_answer, docs) → answerable + optional reason. |
| `src/backend/services/agent_service.py` or pipeline module | After subanswer generation, call verification; set SubQuestionAnswer.answerable (and reason). |

**How to test:** Unit: sub-answer contradicting docs → answerable False (or low score). Integration: subanswer → verification → response includes verification result.

### Implemented
- Added verification fields to `src/backend/schemas/agent.py`:
  - `answerable: bool = False`
  - `verification_reason: str = ""`
- Added new `src/backend/services/subanswer_verification_service.py` with deterministic verification:
  - Marks unanswerable when the subanswer reports insufficient evidence.
  - Marks unanswerable when no reranked docs are parseable.
  - Computes token overlap between subanswer and reranked evidence to check grounding.
  - Returns `SubanswerVerificationResult(answerable, reason)`.
- Updated `src/backend/services/agent_service.py`:
  - Wired a new stage `_apply_subanswer_verification_to_sub_qa(...)` after subanswer generation.
  - Preserves reranked retrieval output and uses it as verification evidence.
  - Stores verification output in `SubQuestionAnswer.answerable` and `SubQuestionAnswer.verification_reason`.
  - Added verification visibility logs per sub-question and in run-end summary.
- Updated tests:
  - New: `src/backend/tests/services/test_subanswer_verification_service.py`
  - Updated: `src/backend/tests/services/test_agent_service.py`
  - Updated: `src/backend/tests/api/test_agent_run.py`

### Validation and logs
- Fresh full restart before work:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Backend tests for Section 9:
  - `docker compose exec backend sh -lc 'uv pip install pytest && uv run pytest tests/services/test_subanswer_verification_service.py tests/services/test_agent_service.py tests/api/test_agent_run.py'`
  - Result: `14 passed`
- Smoke selector command:
  - `docker compose exec backend sh -lc 'uv run pytest tests/api -m smoke'`
  - Result: `3 deselected` (no smoke-selected tests)
- Runtime health + logs:
  - `curl http://localhost:8001/api/health` -> `{"status":"ok"}`
  - `docker compose ps` -> `backend`, `frontend`, `db`, `chrome` all `Up` (`db` healthy)
  - `docker compose logs --tail=140 backend`, `--tail=80 frontend`, `--tail=80 db`
- Backend log evidence for this section:
  - `Per-subquestion subanswer verification start count=...`
  - `Per-subquestion subanswer verification sub_question=... answerable=... reason=...`
  - `SubQuestionAnswer[...] ... answerable=... verification_reason=...`

**Test results:** Complete.
## Section 10: Parallel sub-question processing

**Single goal:** Run the per-subquestion pipeline (expansion -> search -> validation -> rerank -> subanswer -> verification) for all sub-questions in parallel.

**Details:**
- Given sub-questions from decomposition (Section 3), run Sections 4-9 for each sub-question in parallel (thread pool, asyncio, or task graph). No shared mutable state across sub-questions; each yields one SubQuestionAnswer with sub_answer and verification. Use minimal executor (e.g. concurrent.futures) if no orchestration yet. No initial-answer assembly or refinement here.

**Tech:** concurrent.futures or asyncio (stdlib), or existing orchestration. Add new dependency to pyproject.toml if needed. No Docker change.

**Files**

| File | Purpose |
|------|--------|
| `src/backend/services/agent_service.py` or new `src/backend/services/subquestion_pipeline.py` | run_pipeline_for_subquestions(sub_questions, ...) -> expansion->...->verification per sub-question in parallel; return list of SubQuestionAnswer. |
| `src/backend/services/agent_service.py` | After decomposition, invoke parallel pipeline; pass results to initial-answer generation. |

**How to test:** Unit: 2+ sub-questions with mocks -> both complete, results ordered/keyed; wall-clock < sequential. Integration: multiple sub-questions -> all sub_qa populated, verification set.

### Implemented
- Added `run_pipeline_for_subquestions(...)` in `src/backend/services/agent_service.py` using `ThreadPoolExecutor` + `as_completed`.
- Added `_run_pipeline_for_single_subquestion(...)` to run per-item validation -> rerank -> subanswer -> verification in sequence, with a deep-copied item to avoid shared mutable state.
- Kept output deterministic by storing future results at their original index before returning.
- Updated `run_runtime_agent(...)` to call `run_pipeline_for_subquestions(...)` instead of sequential list-wide processing.
- Added parallelization logs:
  - pipeline parallel start (count/configured workers/effective workers)
  - per-item start and complete (including verification result)
  - pipeline parallel complete.
- Added tests in `src/backend/tests/services/test_agent_service.py`:
  - `test_run_pipeline_for_subquestions_runs_in_parallel_and_preserves_order`
  - `test_run_runtime_agent_populates_multiple_subquestions_with_verification`

### Validation and logs
- Fresh full restart before work:
  - `docker compose down -v --rmi all`
  - `docker compose build`
  - `docker compose up -d`
- Backend test execution in container failed because `pytest` is not in backend dependencies:
  - `docker compose exec backend uv run pytest tests/services/test_agent_service.py`
  - Result: `error: Failed to spawn: pytest (No such file or directory)`
- Required section tests run in backend workspace with transient pytest install via uv:
  - `cd src/backend && uv run --with pytest pytest tests/services/test_agent_service.py`
  - Result: `12 passed in 11.58s`
- Container restart after code changes:
  - `docker compose restart backend`
  - `docker compose ps` showed `backend`, `frontend`, `chrome` up and `db` healthy.
- Health/log checks:
  - `curl http://localhost:8001/api/health` -> `{"status":"ok"}`
  - `docker compose logs --tail=120 backend`
  - `docker compose logs --tail=60 frontend`
  - `docker compose logs --tail=60 db`
- Backend log evidence included startup/reload with no runtime errors after final restart.

**Test results:** Complete.

## Section 11: Initial answer generation

**Single goal:** Produce the initial answer from initial search results (Section 2) and sub-question answers (Section 10).

**Details:**
- Input: user question, initial-search context, list of SubQuestionAnswer. Output: one initial answer string. LLM (coordinator or synthesizer) uses both initial docs and sub_qa. No refinement decision or refinement decomposition here.

**Tech:** Existing LLM and coordinator/synthesizer. No new packages. No Docker change.

**Files**

| File | Purpose |
|------|--------|
| `src/backend/services/agent_service.py` | After parallel pipeline, call initial-answer generation with question + initial context + sub_qa; set response.output (or state for refinement). |
| `src/backend/agents/coordinator.py` (optional) | If coordinator produces initial answer, feed it initial-search context and sub_qa; else dedicated synthesizer. |

**How to test:** Unit: fixed initial context + sub_qa → initial answer non-empty, aligned with inputs. Integration: full flow → response.output is initial answer (no refinement yet).

### Implemented
- Added `src/backend/services/initial_answer_service.py` with `generate_initial_answer(...)`:
  - Synthesizes initial answer from `main_question + initial_search_context + sub_qa`.
  - Uses `ChatOpenAI` (`INITIAL_ANSWER_MODEL`, default `gpt-4.1-mini`) when API key exists.
  - Provides deterministic fallback when LLM is unavailable, prioritizing verified subanswers and then initial context snippets.
  - Added explicit logs for stage start, fallback usage, and LLM completion.
- Updated `src/backend/services/agent_service.py`:
  - Wired Section 11 synthesis after per-subquestion parallel pipeline completes.
  - Captures/logs coordinator raw output separately for visibility.
  - Sets `response.output` from `generate_initial_answer(...)` instead of raw coordinator last message.
- Updated `src/backend/tests/services/test_agent_service.py`:
  - Runtime tests now assert Section 11 synthesized output path and synthesis inputs.
  - Added log assertion for `Coordinator raw output captured`.
- Added `src/backend/tests/services/test_initial_answer_service.py`:
  - Validates fallback synthesis from verified subanswers.
  - Validates fallback synthesis from initial context when subanswers are absent.

### Validation and useful logs
- Restarted changed container:
  - `docker compose restart backend`
- Unit tests:
  - `docker compose exec backend sh -lc 'uv pip install pytest && uv run pytest tests/services/test_initial_answer_service.py tests/services/test_agent_service.py'`
  - Result: `14 passed`
- Integration data prep:
  - `POST /api/internal-data/wipe` -> `{"status":"success","message":"All internal documents and chunks removed."}`
  - `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` -> `{"status":"success","documents_loaded":1,"chunks_created":14,...}`
- Integration run:
  - `POST /api/agents/run` with `{"query":"What changed in NATO policy?"}` -> `HTTP 200`
  - Response included populated `sub_qa` and synthesized `output`.
- Backend log evidence:
  - `Coordinator raw output captured output_length=1330 ...`
  - `Initial answer generation start question_len=28 context_items=5 sub_qa_count=11`
  - `Initial answer generation complete via LLM answer_len=579 model=gpt-4.1-mini`
  - `Runtime agent run complete output_length=579 ...`
- Frontend/DB logs checked (`docker compose logs --tail ... frontend db`) with no new runtime errors related to this change.

**Test results:** Complete.

## Section 12: Refinement decision

**Single goal:** Decide if the initial answer is lacking; set “refinement needed” (and optional reason) to trigger the refinement path (Section 13).

**Details:**
- Input: user question, **initial answer (Section 11)**, and **sub_qa (Section 9)**. Both the initial answer and sub_qa are required: we evaluate the initial answer and the per-sub-question results (answerable/unanswerable, verification) together. Output: refinement_needed: bool, optional reason. LLM or rule-based (e.g. “no relevant found”, low verification). Expose to next step only; no refinement decomposition or answer here.

**Tech:** LLM if used. No new packages. No Docker change.

**Files**

| File | Purpose |
|------|--------|
| New `src/backend/services/refinement_decision_service.py` or equivalent | should_refine(question, initial_answer, sub_qa) → (refinement_needed: bool, reason: str). |
| `src/backend/services/agent_service.py` | After initial answer, call refinement decision; if refinement_needed → Section 13; else return initial answer as final. |

**How to test:** Unit: initial answer “no relevant docs” → refinement_needed True; complete answer → False. Integration: weak initial answer → refinement path taken.

### Implemented
- Added `src/backend/services/refinement_decision_service.py`:
  - Introduced `RefinementDecision` dataclass.
  - Implemented `should_refine(question, initial_answer, sub_qa)` with rule-based checks for:
    - empty or insufficient-evidence initial answer,
    - missing sub-question answers,
    - zero answerable sub-answers,
    - low answerable ratio (configurable via `REFINEMENT_MIN_ANSWERABLE_RATIO`, default `0.5`).
- Updated `src/backend/services/agent_service.py`:
  - Calls `should_refine(...)` immediately after initial-answer generation.
  - Added visibility logs for decision outcome and reason.
  - Added explicit branch log when refinement is flagged (Section 13 handoff point).
- Added tests:
  - New `src/backend/tests/services/test_refinement_decision_service.py` with required true/false unit coverage.
  - Updated `src/backend/tests/services/test_agent_service.py` with a runtime-flow test that asserts refinement-flag branch logging.

### Validation and logs
- Container refresh for code changes:
  - `docker compose restart backend`
- Unit tests:
  - `docker compose exec backend sh -lc 'uv pip install pytest && uv run pytest tests/services/test_refinement_decision_service.py tests/services/test_agent_service.py'`
  - Result: `15 passed`
- Integration (weak-answer scenario):
  - `POST /api/internal-data/wipe` -> `{"status":"success","message":"All internal documents and chunks removed."}`
  - `POST /api/agents/run` with `{"query":"What happened in policy XZQ-999 with no indexed data?"}` -> `200`
  - Response had only unanswerable `sub_qa` items and sparse output context.
- Backend logs confirmed Section 12 behavior:
  - `Refinement decision computed refinement_needed=True reason=no_answerable_subanswers sub_qa_count=2`
  - `Refinement path flagged but deferred until Section 13 implementation reason=no_answerable_subanswers`
  - `Runtime agent run complete output_length=246 ...`
- Container log sweep and state checks:
  - `docker compose logs --tail=200 backend`
  - `docker compose logs --tail=80 frontend`
  - `docker compose logs --tail=80 db`
  - `docker compose ps` -> all services up; `db` healthy.

**Test results:** Complete.

## Section 13: Refinement decomposition

**Single goal:** Produce a new list of refined sub-questions that target gaps and unanswerable sub-questions. Run only when refinement_needed (Section 12). Refined sub-questions are then run through the full per-subquestion pipeline in Section 14.

**Details:**
- Input: user question, initial answer (Section 11), SubQuestionAnswer list (Section 9; with answerable/verification). Output: list of refined sub-questions. We do not re-ask the same sub-questions; the LLM uses the initial answer and sub_qa (including which were unanswerable) to generate gap-targeting sub-questions. No retrieval or synthesis here; output feeds Section 14.

**Tech:** Existing LLM. No new packages. No Docker change.

**Files**

| File | Purpose |
|------|--------|
| New `src/backend/services/refinement_decomposition_service.py` or equivalent | refine_subquestions(question, initial_answer, sub_qa) -> list[str]. |
| `src/backend/services/agent_service.py` | When refinement_needed (Section 12), call refinement decomposition; pass refined sub-questions to Section 14. |

**How to test:** Unit: initial answer with gap + unanswerable sub-questions -> refined sub-questions target gap. Integration: refinement_needed=True -> refined sub-questions passed to next step.

### Implemented
- Added `src/backend/services/refinement_decomposition_service.py` with `refine_subquestions(...)`:
  - LLM-first refined-subquestion generation (`gpt-4.1-mini` by default) from `question + initial_answer + sub_qa`.
  - Strict sanitization: normalize to full questions ending in `?`, dedupe, filter out existing sub-questions, cap by `REFINEMENT_DECOMPOSITION_MAX_SUBQUESTIONS`.
  - Deterministic fallback generation for no-key/error paths based on unanswerable sub-questions and verification reasons.
  - Added explicit start/completion logs for both LLM and fallback execution paths.
- Updated `src/backend/services/agent_service.py` refinement branch:
  - Replaced Section-13 deferred branch with a real call to `refine_subquestions(...)` when `refinement_needed=True`.
  - Added visibility logs for count + each refined sub-question and Section 14 handoff readiness.
- Added tests:
  - New `src/backend/tests/services/test_refinement_decomposition_service.py`.
  - Updated `src/backend/tests/services/test_agent_service.py` to assert `refine_subquestions(...)` is called on refinement and handoff logs are emitted.

### Validation and useful logs
- Restarted changed container:
  - `docker compose restart backend`
- Unit tests:
  - `docker compose exec backend uv run pytest tests/services/test_refinement_decomposition_service.py tests/services/test_agent_service.py`
  - Result: `15 passed`
- Backend smoke selector:
  - `docker compose exec backend uv run pytest tests/api -m smoke`
  - Result: `3 deselected` (no smoke-selected tests)
- Integration run:
  - `POST /api/agents/run` with `{"query":"What changed in policy?"}` -> `200`
- Backend log evidence:
  - `Refinement decision computed refinement_needed=True reason=no_answerable_subanswers sub_qa_count=11`
  - `Refinement decomposition start question_len=23 initial_answer_len=312 sub_qa_count=11`
  - `Refinement decomposition complete via LLM count=6 model=gpt-4.1-mini`
  - `RefinedSubQuestion[1]=What documents or sources detail the policy before the change?`
  - `RefinedSubQuestion[2]=Are there any official statements or press releases about the policy change?`
  - `RefinedSubQuestion[3]=What are the legal or regulatory frameworks governing the policy?`
  - `RefinedSubQuestion[4]=Has there been any public or stakeholder feedback regarding the policy change?`
  - `RefinedSubQuestion[5]=What are the timelines or deadlines associated with implementing the policy changes?`
  - `RefinedSubQuestion[6]=Are there any related policies that might have influenced the changes?`
  - `Refined sub-questions prepared for Section 14 handoff count=6`
- Container and log checks:
  - `docker compose ps` -> all services up; `db` healthy.
  - `docker compose logs --tail=220 backend`
  - `docker compose logs --tail=80 frontend`
  - `docker compose logs --tail=120 db`

**Test results:** Complete.

## Section 14: Refinement answer path

**Single goal:** Run the same per-subquestion pipeline (Sections 4–9) on the refined sub-questions from Section 13, then synthesize the refined final answer. When refinement was taken, this is the final output.

**Details:**
- Input: refined sub-questions (Section 13). Reuse the same pipeline as Section 10 (expand -> search -> validate -> rerank -> answer -> check) for each refined sub-question in parallel. Output: refined answer (synthesizer combining refined sub-answers and optionally initial answer). response.output = refined answer when refinement was taken (optional initial_answer in metadata).

**Tech:** Reuse pipeline and LLM from Sections 4–11. No new dependencies. No Docker change.

**Files**

| File | Purpose |
|------|--------|
| `src/backend/services/agent_service.py` | On refinement path: call same parallel sub-question pipeline (Section 10) with refined sub-questions; synthesizer -> refined answer; response.output = refined answer. |
| `src/backend/schemas/agent.py` (optional) | Optional response fields for initial_answer and refined_answer if both returned to client. |

**How to test:** Unit: mocks + refined sub-questions -> pipeline invoked, refined answer non-empty. Integration: refinement_needed=True -> final response.output is refined answer; sub_qa/metadata reflect refined sub-questions and answers.

### Implemented
- Updated `src/backend/services/agent_service.py`:
  - Added `_seed_refined_sub_qa_from_retrieval(...)` to retrieve docs for refined sub-questions in parallel and seed `SubQuestionAnswer` entries.
  - Added `_format_retrieved_documents_for_pipeline(...)` so refined retrieval uses the same parseable format as retriever tool output.
  - Wired refinement branch to run Section 14 end-to-end:
    - refined sub-question retrieval
    - existing parallel sub-question pipeline (`run_pipeline_for_subquestions`)
    - refined synthesis via `generate_initial_answer(...)`
    - final response override (`response.output` and `response.sub_qa`) with refined results when refinement executes.
  - Added explicit visibility logs for refinement retrieval and refinement answer completion.
- Updated `src/backend/tests/services/test_agent_service.py`:
  - Added `test_seed_refined_sub_qa_from_retrieval_builds_retrieved_payloads`.
  - Updated refinement-path runtime test to assert second-stage synthesis runs and final output uses refined synthesis.

### Validation and useful logs
- Restarted changed container:
  - `docker compose restart backend`
- Unit tests:
  - `docker compose exec backend sh -lc 'uv run python -m pytest tests/services/test_agent_service.py'`
  - Result: `14 passed`
- Backend smoke selector:
  - `docker compose exec backend sh -lc 'uv run python -m pytest tests/api -m smoke'`
  - Result: `3 deselected` (no smoke-selected tests)
- Integration data prep:
  - `POST /api/internal-data/wipe` -> `{"status":"success","message":"All internal documents and chunks removed."}`
  - `POST /api/internal-data/load` with `{"source_type":"wiki","wiki":{"source_id":"nato"}}` -> `{"status":"success","documents_loaded":1,"chunks_created":14}`
- Integration run:
  - `POST /api/agents/run` with `{"query":"What changed in policy?"}` -> `200`
  - Response returned populated `sub_qa` and synthesized `output`.
- Backend logs (tail) included:
  - `Per-subquestion pipeline parallel start count=5 configured_max_workers=4 effective_workers=4`
  - `Per-subquestion pipeline parallel complete count=5`
  - `Initial answer generation start question_len=23 context_items=5 sub_qa_count=5`
  - `Refinement decision computed refinement_needed=False reason=sufficient_answerable_ratio:1.00 sub_qa_count=5`
  - `Runtime agent run complete output_length=586 ...`
- Frontend logs (tail) showed Vite dev server healthy (`VITE v5.4.21 ready`).
- DB logs (tail) showed DB healthy; no runtime errors tied to Section 14 changes.

**Test results:** Complete.
