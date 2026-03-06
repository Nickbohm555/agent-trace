# Agent-Trace Implementation Plan

Tasks are in **recommended implementation order** (1…n). Each section = **one context window**. Complete one section at a time. Sections 22–23 add UI to run the tracer and view results.

**Current section to work on:** Section 23.

---

## Tracing deep-agent (harness engineering)

The following sections implement a **tracing deep-agent** that consumes traces from Langfuse, has access to the target agent's codebase (sandboxed), and applies harness improvements (boosting). The tracer is a LangGraph **deep-agent** with a plan–build–verify–fix loop; tools: read trace, list/read/edit codebase, run commands; middleware: verification, time budget, loop detection. Prefer extending LangChain `create_deep_agent` with tracer tools and middleware; otherwise implement a ReAct-style graph with state, virtual filesystem (sandbox), task delegation, and **Trace Analyzer Skill** (fetch traces → parallel error analysis → synthesize → harness change output). **Langfuse:** Use the same project as the traced app (e.g. agent-search)—same `LANGFUSE_*` env vars so traces are visible. Trace IDs come from the Langfuse UI or API; the tracer accepts `run_id` or `trace_ids` (Section 21). **Setup:** `.env` with `LANGFUSE_*`; default target repo `https://github.com/Nickbohm555/agent-search` via `TRACER_DEFAULT_TARGET_REPO_URL` when URL is omitted (Section 3, Section 21).

---

## Section 1: Langfuse trace ingestion

**Depends on:** None.

**Single goal:** Ingest traces from Langfuse for a given run or experiment so the tracer can analyze errors.

**Deep-agent capability:** Trace Analyzer Skill (data input); tools & context (traces as observation for the tracer).

**Details:**
- **Deep-agent approach:** Traces are the observation/feedback signal for the tracer (Trace Analyzer Skill step 1). Normalized output is what the deep-agent graph will consume via a `read_trace` tool and/or initial state.
- Call Langfuse API (or SDK) to fetch traces for a specified run/project/environment.
- Support filtering by trace ID, run name, or time range.
- Normalize trace payload (spans, inputs, outputs, errors, latency) into an internal representation.
- No persistence required in this section; output is in-memory or returned to caller.

**Tech stack and dependencies**
- Libraries: `langfuse` (or `langfuse-sdk`) in `pyproject.toml`; use existing `.env` / `LANGFUSE_*` from `.env.example`.
- Tooling: no Docker/tooling changes.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/services/langfuse_trace_service.py | Fetch and normalize Langfuse traces. |
| src/backend/schemas/trace.py | Pydantic models for normalized trace/span/error. |

**How to test:** Unit tests: mock Langfuse client, assert normalized schema; optional integration test with LANGFUSE_ENABLED and real project if configured.

**Test results:** `docker compose exec backend uv run pytest tests/services/test_langfuse_trace_service.py` → 3 passed (2026-03-06).

---

## Section 2: Trace schema and storage for analysis

**Depends on:** Section 1 (ingestion and normalized schema).

**Single goal:** Define a persistent schema for traces and store ingested traces so the tracer and parallel analyzers can query them.

**Deep-agent capability:** Context/trace persistence; enables tracer and subagents to load traces by run/experiment.

**Details:**
- **Deep-agent approach:** Persistent trace storage backs both the main tracer and parallel error-analysis subagents (harness task delegation). Load-by-run/experiment is the context the graph and subagents need.
- Store normalized traces (and optionally raw payload) in Postgres (or dedicated table).
- Schema supports: trace_id, run_id, spans, tool_calls, errors, timestamps, token/cost if available.
- Provide a read API or service method to load traces by run/experiment for the tracer.

**Tech stack and dependencies**
- Alembic migration for new table(s); existing `db.py` and `models.py`.
- No new pip packages beyond Section 1 if trace schema lives in DB.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/models.py | ORM models for trace/trace_span (or equivalent). |
| src/backend/schemas/trace.py | Extend with storage DTOs if needed. |
| src/backend/services/trace_storage_service.py | Save/load traces by run or experiment. |
| src/backend/alembic/versions/xxx_add_traces.py | Migration for trace tables. |

**How to test:** Unit tests for storage service; migration up/down; load traces after ingest (Section 1) and assert round-trip.

**Test results:**
- `docker compose exec backend uv run alembic downgrade base && docker compose exec backend uv run alembic upgrade head && docker compose exec backend uv run alembic current` → downgraded and re-upgraded successfully, current revision `20260306_01` (2026-03-06).
- `docker compose exec backend uv run pytest tests/services/test_langfuse_trace_service.py tests/services/test_trace_storage_service.py` → 6 passed (2026-03-06).

---

## Section 3: Sandbox runtime for target repo

**Depends on:** None.

**Single goal:** Provide an isolated environment (sandbox) where the target agent’s repo is cloned and all tracer-driven edits and commands run. When no URL is supplied by the caller, use the configured default.

**Deep-agent capability:** Code execution environment; virtual filesystem backend (sandbox as pluggable backend for list/read/edit/execute).

**Details:**
- **Deep-agent approach:** Sandbox implements the harness **code execution** and **virtual filesystem** backend: the tracer’s `ls`/`read_file`/`edit_file`/`execute` tools operate on this backend (same contract as [deepagents sandboxes](https://docs.langchain.com/oss/python/deepagents/sandboxes)). One sandbox per run; disposable and isolated.
- **Configure tracer to target repo:** Read `TRACER_DEFAULT_TARGET_REPO_URL` from env (default `https://github.com/Nickbohm555/agent-search`). When creating a sandbox, use the URL from the run request or, if omitted, this default. Add `TRACER_DEFAULT_TARGET_REPO_URL` to `.env.example`.
- Clone or mount the target repo into a sandbox (e.g. temp directory with isolation, or Docker container).
- Sandbox is disposable per tracer run; tracer has read/write and execute within the sandbox only.
- Interface: get sandbox path, run command in sandbox, apply file patch or read file.

**Tech stack and dependencies**
- Option A: subprocess + temp dir with `git clone` or copy; Option B: Docker (e.g. `docker run` with volume mount). Document choice in section.
- No new pip deps if using stdlib + subprocess; add `docker` SDK only if using Docker-based sandbox.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/services/sandbox_service.py | Create sandbox, run command, read/write files, teardown; use default target repo from config when URL not supplied. |
| src/backend/schemas/sandbox.py | Request/response types for sandbox operations. |
| .env.example | Add `TRACER_DEFAULT_TARGET_REPO_URL=https://github.com/Nickbohm555/agent-search`. |

**How to test:** Unit test: create sandbox, write file, run `echo`, read file, teardown. Assert sandbox creation uses `TRACER_DEFAULT_TARGET_REPO_URL` when no URL is passed. No network or host filesystem outside sandbox in test.

**Test results:** `docker compose exec backend uv run pytest tests/services/test_sandbox_service.py` → 3 passed (2026-03-06).

---

## Section 4: LangGraph tracer deep-agent graph skeleton

**Depends on:** None (foundation for Sections 5–15).

**Single goal:** Implement the tracer as a LangGraph **deep-agent** graph with entry, agent node(s), and conditional edges. **Do not add tools or middleware in this section**—only the graph backbone.

**Deep-agent capability:** Planning (graph backbone); ReAct-style agent loop with shared state and conditional routing (continue vs end).

**Details:**
- **Graph shape (deep-agent approach):** ReAct loop: start → agent node → conditional edge → tools node (when tool_calls present) → back to agent, or → END when no tool_calls. This matches the [LangGraph ReAct pattern](https://oboe.com/learn/agentic-workflows-with-langgraph-d5lisb/cyclic-control-flow-uhdgom) and the structure underlying `create_deep_agent` (reason → act → observe → repeat until done). State and conditional edges are the standard way to implement this.
- **State:** TypedDict (or equivalent) with at least: `messages`, `current_trace_summary`, `run_id`. Optionally include a task-list field for plan–build–verify–fix progress (harness “Planning capabilities” use a `write_todos`-style list in state; can add the tool in a later section).
- Use LangGraph `StateGraph`; **no tools or middleware attached in this section.** One agent node, one conditional edge (e.g. `should_continue` → `"continue"` | `"end"`). Tools and middleware are added in later sections.
- **Preferred (deep-agent approach):** Build on [`create_deep_agent`](https://reference.langchain.com/python/deepagents/graph/create_deep_agent) and extend with tracer-specific tools and middleware in subsequent sections. **Alternative:** Build a custom LangGraph `StateGraph` with the same ReAct shape (agent → conditional → tools | END) and state schema if not using the library.

**Tech stack and dependencies**
- Add `langgraph`, `langchain-core`, `langchain-openai` (or chosen LLM); optionally `deepagents` if using `create_deep_agent`. Add to `pyproject.toml`.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/langgraph_agent.py | Build and export the LangGraph tracer graph (skeleton only). |
| src/backend/agents/tracer_state.py | State schema for tracer graph. |

**How to test:** Invoke graph with dummy state; assert one agent step and transition; no tools called. Graph is the deep-agent backbone.

**Test results:** `docker compose exec backend uv run pytest tests/agents/test_langgraph_agent.py` → 2 passed (2026-03-06).

---

## Section 5: Reasoning budget configuration

**Depends on:** Section 4 (graph exists to receive config).

**Single goal:** Make reasoning compute configurable (e.g. high for planning and verification, lower for implementation) to balance quality and token/time (per article “reasoning sandwich”).

**Deep-agent capability:** Context and token management — reasoning budget; configurable reasoning level and optional “reasoning sandwich.”

**Details:**
- **Deep-agent approach:** Harness **context and token management** — configurable reasoning budget (per [article](https://blog.langchain.com/improving-deep-agents-with-harness-engineering/) “reasoning sandwich”): higher for planning and verification, lower for implementation. Pass via run config or state into the LLM/adapter; abstract so any backend can respect it.
- Support a config flag or run config for “reasoning level” (e.g. low/medium/high/xhigh if the model supports it). Article baseline: **xhigh–high–xhigh** (planning and verification at highest, implementation at high).
- Optionally: use higher reasoning for first and last phases (planning, verification) and lower for middle (implementation); document the heuristic.
- No requirement to integrate a specific model API; abstract so different backends can respect the setting.

**Tech stack and dependencies**
- Config in state or run config; model client must support parameter if applicable.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/tracer_config.py | Reasoning budget / level and phase mapping. |
| src/backend/agents/langgraph_agent.py | Pass reasoning config to LLM or adapter. |

**How to test:** Run with different configs; assert LLM receives different params or that config is read correctly (mock if needed).

**Test results:** `docker compose exec backend uv run pytest tests/agents/test_langgraph_agent.py tests/agents/test_tracer_config.py` → 7 passed (2026-03-06).

---

## Section 6: Tracer tool – read trace

**Depends on:** Sections 1, 2 (ingestion and storage), Section 4 (graph to bind tool).

**Single goal:** Add a tool the tracer agent can call to read fetched trace content (errors, spans, inputs/outputs).

**Deep-agent capability:** Tools — trace read (observation/feedback signal for the tracer).

**Details:**
- **Deep-agent approach:** Implement as a tool bound to the deep-agent graph (same binding pattern as harness tools). The agent calls it to observe trace content; output is the observation for the next reason step.
- Tool input: run_id or trace_id (or both).
- Tool output: structured summary of trace: errors, failed spans, key inputs/outputs, token/latency if present.
- Tool is registered with the tracer graph and available in the agent node.

**Tech stack and dependencies**
- Tool uses trace storage or Langfuse service from Sections 1–2.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/tools/trace_tools.py | `read_trace` tool implementation. |
| src/backend/agents/langgraph_agent.py | Bind trace tool(s) to the agent. |

**How to test:** Unit test tool with mocked trace data; integration: run graph, agent calls tool, state contains trace summary.

**Test results:** `docker compose exec backend uv run pytest tests/tools/test_trace_tools.py tests/agents/test_langgraph_agent.py` → 7 passed (2026-03-06).

---

## Section 7: Tracer tools – list and read codebase

**Depends on:** Section 3 (sandbox), Section 4 (graph).

**Single goal:** Give the tracer agent tools to list directories and read files in the sandboxed target repo.

**Deep-agent capability:** Virtual filesystem — list directory, read file (with sandbox root).

**Details:**
- **Deep-agent approach:** Match harness [virtual filesystem](https://docs.langchain.com/oss/python/deepagents/harness#virtual-filesystem-access) tools: `ls` and `read_file` backed by the sandbox (Section 3). Same semantics as deepagents’ filesystem backend (path relative to sandbox root, metadata for list).
- `list_directory(sandbox_path, path)` – list entries under path within sandbox.
- `read_file(sandbox_path, path)` – return file content; respect sandbox root.
- Both operate on the active sandbox for the current run.

**Tech stack and dependencies**
- Sandbox service (Section 3) for all file/dir operations.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/tools/codebase_tools.py | `list_directory`, `read_file` implementations. |
| src/backend/agents/langgraph_agent.py | Bind codebase tools to the agent. |

**How to test:** Unit tests with mock sandbox; integration: agent lists dir and reads file in sandbox.

**Test results:** `docker compose exec backend uv run pytest tests/tools/test_codebase_tools.py tests/services/test_sandbox_service.py tests/agents/test_langgraph_agent.py` → 11 passed (2026-03-06).

---

## Section 8: Tracer tool – edit file in sandbox

**Depends on:** Section 3 (sandbox), Section 4 (graph). Same module as Section 7 for codebase tools.

**Single goal:** Add a tool for the tracer to apply edits (patch or full replace) to files in the sandboxed repo.

**Deep-agent capability:** Virtual filesystem — edit_file / write_file (all writes scoped to sandbox).

**Details:**
- **Deep-agent approach:** Harness virtual filesystem `edit_file` / `write_file` backed by sandbox; all writes scoped to the sandbox backend (no host filesystem). Same contract as deepagents’ filesystem tools.
- Tool: `edit_file(sandbox_path, path, content)` or `apply_patch(sandbox_path, path, patch)`.
- All writes go through sandbox service; no writes outside sandbox.

**Tech stack and dependencies**
- Sandbox service (Section 3) must support write; codebase tools can live in same module as Section 7.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/tools/codebase_tools.py | `edit_file` or `apply_patch` implementation. |
| src/backend/agents/langgraph_agent.py | Bind edit tool to the agent. |

**How to test:** Unit test: apply edit in sandbox, read file back, assert content. Integration: agent edits file in graph run.

**Test results:** `docker compose exec backend uv run pytest tests/tools/test_codebase_tools.py tests/agents/test_langgraph_agent.py` → 9 passed (2026-03-06).

---

## Section 9: Tracer tool – run command in sandbox

**Depends on:** Section 3 (sandbox), Section 4 (graph).

**Single goal:** Add a tool for the tracer to run shell commands (e.g. tests, linters) inside the sandbox.

**Deep-agent capability:** Code execution — execute tool (run command in isolated sandbox; stdout/stderr, exit code, timeout).

**Details:**
- **Deep-agent approach:** Harness **code execution** — the `execute` tool for the sandbox backend ([deepagents code execution](https://docs.langchain.com/oss/python/deepagents/harness#code-execution)). Returns combined stdout/stderr, exit code; timeout to avoid runaway processes; optionally truncate large output and write to a file for the agent to read.
- Tool: `run_command(sandbox_path, command, timeout_sec)`.
- Return stdout, stderr, exit code. Timeout to avoid runaway processes.

**Tech stack and dependencies**
- Sandbox service (Section 3) must support `run_command`; no new deps.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/tools/sandbox_tools.py | `run_command` implementation. |
| src/backend/agents/langgraph_agent.py | Bind run_command tool to the agent. |

**How to test:** Unit test: run `echo hello` in sandbox, assert stdout. Integration: agent runs tests in sandbox.

**Test results:** `docker compose exec backend uv run pytest tests/agents/test_langgraph_agent.py tests/agents/test_tracer_prompts.py` → 10 passed (2026-03-06).

---

## Section 10: Tracer system prompt – plan, build, verify, fix

**Depends on:** Section 4 (graph to inject prompt).

**Single goal:** Implement the tracer’s system prompt with Planning & Discovery, Build, Verify, Fix and a strong focus on testing (per article).

**Deep-agent capability:** System prompts — plan–build–verify–fix; self-verification and testing as first-class phases.

**Details:**
- **Deep-agent approach:** This is the **custom system prompt** for the tracer (prepended to base agent prompt as in [harness prompts](https://docs.langchain.com/oss/python/deepagents/harness#prompts)). It defines plan–build–verify–fix and self-verification so the agent’s reasoning follows the [article’s loop](https://blog.langchain.com/improving-deep-agents-with-harness-engineering/); middleware (Sections 12–15) enforces behavior at the edges. The article’s main failure mode: “the agent wrote a solution, re-read its own code, confirmed it looks ok, and stopped”—so Verify must compare against the task spec, not only the agent’s own code.
- Planning & Discovery: read task (trace/task spec), scan codebase, plan and define how to verify the solution.
- Build: implement with verification in mind; build tests if missing; happy path and edge cases.
- Verify: run tests, read full output, **compare against what was asked (not against your own code)** (per article).
- Fix: analyze errors, revisit spec, fix issues.
- Prompt is the single source of instructions for the tracer’s reasoning; no middleware logic in prompt.

**Tech stack and dependencies**
- Prompt lives in code or template file; no new packages.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/tracer_prompts.py | System prompt and any task-specific prompt fragments. |
| src/backend/agents/langgraph_agent.py | Load and inject system prompt into the agent. |

**How to test:** Assert prompt contains required phases and verification/testing language; optional: run graph and check that agent behavior aligns (manual or snapshot).

**Test results:** `docker compose exec backend uv run pytest tests/agents/test_tracer_prompts.py` → 3 passed (2026-03-06).

---

## Section 11: Teaching testable code in tracer prompt

**Depends on:** Section 10 (existing system prompt to extend).

**Single goal:** Add prompt instructions that work will be measured against programmatic tests, file paths must be exact, and edge cases matter (per article).

**Deep-agent capability:** System prompts — testable code, exact file paths, edge cases (not only happy path).

**Details:**
- **Deep-agent approach:** Extend the tracer’s **system prompt** (Section 10) with harness-style “teaching testable code” instructions (per [article](https://blog.langchain.com/improving-deep-agents-with-harness-engineering/)): work measured by programmatic tests, exact file paths so solutions work in automated scoring, edge cases not only happy path. No new graph or middleware—prompt-only addition.
- Explicit instructions: follow task spec file paths exactly; write testable code; consider edge cases, not only happy path.
- Integrate into the existing tracer system prompt without duplicating the full prompt.

**Tech stack and dependencies**
- Prompt-only change in `tracer_prompts.py`.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/tracer_prompts.py | Add testable-code and edge-case instructions. |

**How to test:** Assert prompt text contains file-path exactness, programmatic tests, edge cases.

**Test results:** `docker compose exec backend uv run pytest tests/agents/test_tracer_prompts.py` → 3 passed (2026-03-06).

---

## Section 12: Local context injection for tracer

**Depends on:** Section 3 (sandbox), Section 4 (graph).

**Single goal:** On tracer start, inject context about the sandbox environment: cwd, directory map, and available tools (e.g. Python path, key binaries).

**Deep-agent capability:** Context management — local context injection (LocalContextMiddleware; onboard agent into environment).

**Details:**
- **Deep-agent approach:** Harness **context management** — [LocalContextMiddleware](https://blog.langchain.com/improving-deep-agents-with-harness-engineering/)-style: run at agent start, inject cwd, directory map, and tool paths into the first message or state so the agent is “onboarded” into its environment (per article).
- Run discovery in sandbox: list top-level dirs, detect Python/node/etc. (e.g. `which python3`, `which pytest`).
- Add this context to the first agent message or state so the tracer does not waste steps discovering the environment.

**Tech stack and dependencies**
- Sandbox service (Section 3) to run `which`/`ls`; no new deps.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/tracer_context.py | Build local context (cwd, dirs, tools). |
| src/backend/agents/langgraph_agent.py | Call context builder at start and inject into state. |

**How to test:** Unit test: given a sandbox path, assert context contains expected keys (cwd, python_path, etc.). Integration: first turn has context in state.

**Test results:** `docker compose exec backend uv run pytest tests/agents/test_tracer_context.py tests/agents/test_langgraph_agent.py` → 11 passed (2026-03-06).

---

## Section 13: Pre-completion verification middleware

**Depends on:** Section 4 (graph to attach middleware).

**Single goal:** Before the tracer can “finish”, run a verification pass (e.g. remind agent to run tests and compare to spec) so the agent does not exit after “code looks ok” without testing.

**Deep-agent capability:** Middleware — pre-completion verification (PreCompletionChecklistMiddleware / Ralph Wiggum–style loop).

**Details:**
- **Deep-agent approach:** Harness [middleware](https://docs.langchain.com/oss/python/langchain/middleware/overview) pattern: a hook that runs before the agent can transition to END. Implements the article’s **PreCompletionChecklistMiddleware**: intercept the agent before it exits and remind it to run a verification pass against the task spec; same idea as a [Ralph Wiggum Loop](https://ghuntley.com/loop/) (force one more turn for verification).
- Hook or middleware that runs when agent intends to end (e.g. “finish” or “submit” action).
- Inject a message or checklist: run verification, run tests, compare to task spec.
- Optionally force one more turn instead of exiting (Ralph Wiggum–style loop for verification).

**Tech stack and dependencies**
- LangGraph: use middleware or conditional edge that checks “has_verified” or injects a verification step before END.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/tracer_middleware.py | Pre-completion checklist / verification hook. |
| src/backend/agents/langgraph_agent.py | Integrate middleware into graph (e.g. before end node). |

**How to test:** Run graph; when agent tries to end, assert verification step runs (e.g. one more message or tool call).

**Test results:** `docker compose exec backend uv run pytest tests/agents/test_tracer_middleware.py tests/agents/test_langgraph_agent.py` → 16 passed (2026-03-06).

---

## Section 14: Time budget injection

**Depends on:** Section 4 (graph to inject into state).

**Single goal:** Inject time-remaining (or step-remaining) warnings into the tracer’s context so the agent shifts to verification and submission under limits.

**Deep-agent capability:** Context management / middleware — time budget injection (nudge toward verification and submit).

**Details:**
- **Deep-agent approach:** Harness context/middleware: inject time-remaining (or step-remaining) into state periodically so the agent shifts to verification and submit (per article: “Time Budgeting”). No hard timeout in this section—only context injection; enforcement can be added later.
- Accept a time budget or max steps per run. Compute remaining time/steps and inject a short message (e.g. “Time remaining: X min; consider running verification and submitting.”) into state periodically.
- Do not implement full timeout enforcement in this section; only context injection.

**Tech stack and dependencies**
- No new deps; use run config or state to track start time / step count.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/tracer_middleware.py | Time-budget message builder and injection. |
| src/backend/agents/langgraph_agent.py | Inject time message at appropriate steps (e.g. every N turns). |

**How to test:** Run with short budget; assert state or messages contain time-remaining text at least once.

**Test results:** `docker compose exec backend uv run pytest tests/agents/test_tracer_middleware.py tests/agents/test_langgraph_agent.py` → 16 passed (2026-03-06).

---

## Section 15: Loop detection middleware

**Depends on:** Section 4 (graph), Section 8 (edit_file tool to hook).

**Single goal:** Track per-file edit counts and, after N edits to the same file, inject a “reconsider your approach” nudge to avoid doom loops (per article).

**Deep-agent capability:** Middleware — loop detection (LoopDetectionMiddleware; tool-call hooks, per-file edit threshold).

**Details:**
- **Deep-agent approach:** Harness [LoopDetectionMiddleware](https://blog.langchain.com/improving-deep-agents-with-harness-engineering/)-style: hook on tool calls (e.g. when `edit_file` is called), increment per-file counter; after threshold inject a “reconsider your approach” nudge to break doom loops (article: “doom loops that make small variations to the same broken approach (10+ times in some traces)”—threshold should account for this).
- Hook on tool calls: when `edit_file` is called, increment counter for that file.
- After threshold (e.g. 5 or 10; article observed 10+ edits to same file), add a system or user message suggesting the agent reconsider the approach for that file.
- Threshold is configurable.

**Tech stack and dependencies**
- LangGraph tool-call hooks or state updates; no new packages.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/tracer_middleware.py | Loop detection state and message injection. |
| src/backend/agents/langgraph_agent.py | Register hook and inject nudge when threshold exceeded. |

**How to test:** Mock or run agent that edits same file N times; assert “reconsider” (or similar) message appears after threshold.

**Test results:** `docker compose exec backend uv run pytest tests/agents/test_tracer_middleware.py tests/agents/test_langgraph_agent.py` → 19 passed (2026-03-06).

---

## Section 16: Parallel error-analysis sub-agents

**Depends on:** Sections 1–2 (traces), Section 4 (graph). Section 17 (harness change schema) can be done before or after; schema is needed for Section 18 synthesis output.

**Single goal:** Spawn multiple worker agents to analyze different trace errors in parallel; main tracer uses their outputs (Trace Analyzer Skill pattern from article).

**Deep-agent capability:** Task delegation (subagents) — parallel error-analysis workers; Trace Analyzer Skill (spawn analyzers → main agent synthesizes).

**Details:**
- **Deep-agent approach:** Harness [task delegation (subagents)](https://docs.langchain.com/oss/python/deepagents/harness#task-delegation-subagents): spawn ephemeral worker agents (one per error or batch), each returns a single structured report; main tracer synthesizes. Use asyncio or LangGraph subgraph so workers run in parallel; context is isolated per worker (Trace Analyzer Skill pattern from the article).
- Given a set of trace errors (or segments), fork N analysis tasks (e.g. one per error or per batch).
- Each worker analyzes one (or a few) errors and returns structured findings (root cause, suggested fix category).
- Main tracer does not run full graph N times; use a parallel execution layer (asyncio or LangGraph subgraph) to run analyzers.

**Tech stack and dependencies**
- LangGraph subgraph or separate invocations; `asyncio.gather` or task pool for parallelism.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/error_analysis_agent.py | Single error-analysis agent or subgraph. |
| src/backend/agents/langgraph_agent.py | Orchestrate parallel analysis and pass results into main tracer state. |

**How to test:** Unit test: run N analyzers with mock errors, assert N results. Integration: tracer run with multiple errors triggers parallel analysis and state receives aggregated findings.

**Test results:** `docker compose exec backend uv run pytest tests/agents/test_error_analysis_agent.py tests/agents/test_langgraph_agent.py` → 15 passed (2026-03-06).

---

## Section 17: Harness change schema

**Depends on:** None (schema only; consumed by Section 18 and API/UI).

**Single goal:** Define a machine-readable schema for suggested harness changes (prompt edits, tool changes, config) so downstream can apply or review.

**Deep-agent capability:** Trace Analyzer Skill — structured harness change schema (prompt/tool/config) for downstream apply or review.

**Details:**
- **Deep-agent approach:** Final step of the Trace Analyzer Skill produces **structured harness change output**—prompt edits, tool changes, config—in a machine-readable schema. No automatic apply; output is for human review or downstream automation. This section defines the schema only; Section 18 produces instances of it.
- Pydantic (or equivalent) models for: suggested prompt edits, tool changes, config changes (e.g. “add to system prompt: …”, “add tool X”, “increase timeout for Y”).
- Output schema: machine-readable (e.g. JSON-serializable) so downstream can apply or review changes.

**Tech stack and dependencies**
- Pydantic schema only; no new runtime deps.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/schemas/harness_changes.py | Pydantic models for suggested prompt/tool/config changes. |

**How to test:** Unit test: instantiate models with sample data; assert serialization/validation.

**Test results:** `docker compose exec backend uv run pytest tests/services/test_trace_analyzer_service.py` → 1 passed (2026-03-06).

---

## Section 18: Synthesis and harness change output

**Depends on:** Sections 16 (parallel analysis), 17 (harness change schema), 4 (graph).

**Single goal:** Main tracer produces structured output (instances of the harness change schema) from synthesized error analysis.

**Deep-agent capability:** Trace Analyzer Skill — synthesis output; main agent produces harness_changes from subagent reports.

**Details:**
- **Deep-agent approach:** After parallel analysis (Section 16), main agent synthesizes findings into a structured report using the schema from Section 17: list of suggested changes (prompt edits, tool changes, config). No automatic application of changes in this section; output only.
- Final node or parser in the graph that converts agent output into `harness_changes` (list of suggested changes conforming to Section 17 schema).

**Tech stack and dependencies**
- Uses `src/backend/schemas/harness_changes.py` from Section 17.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/agents/langgraph_agent.py | Final node or parser that produces harness_changes from agent output. |

**How to test:** Run tracer with mock analysis results; assert output conforms to schema and contains at least one suggestion when errors exist.

**Test results:** `docker compose exec backend uv run pytest tests/agents/test_langgraph_agent.py tests/agents/test_error_analysis_agent.py` → 16 passed (2026-03-06).

---

## Section 19: Trace analyzer orchestration – fetch, analyze, synthesize

**Depends on:** Sections 1, 2, 3, 4–18 (fetch, storage, sandbox, graph with tools/middleware, analysis, synthesis).

**Single goal:** Implement the full Trace Analyzer flow: fetch traces from Langfuse → store or pass to tracer → run parallel error analysis → main agent synthesizes → produce harness change output (single orchestration entry point).

**Deep-agent capability:** Trace Analyzer Skill — full orchestration: fetch traces → store/load → parallel error analysis → synthesize → harness change output (single entry point).

**Details:**
- **Deep-agent approach:** Single **Trace Analyzer Skill** orchestration: fetch traces → store/load → parallel error-analysis subagents (Section 16) → main agent synthesizes → harness change output. The API (Section 21) will call this service. Sandbox created once per run and reused; run_id and target repo passed through.
- Wire Sections 1 (fetch), 2 (load), 3 (sandbox), 4–18 (graph, tools, middleware, analysis, synthesis) into one flow.
- Entry point is a dedicated service method that the API will call.
- Ensure run_id and target repo are passed through; sandbox is created once and reused for the run.

**Tech stack and dependencies**
- No new deps; depends on all prior sections.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/services/trace_analyzer_service.py | Orchestrate fetch → sandbox → parallel analyze → synthesize. |

**How to test:** End-to-end test: mock Langfuse and sandbox; trigger orchestration; assert harness change output and that all steps were invoked in order.

**Test results:**
- `docker compose exec backend uv run pytest tests/services/test_improvement_metrics_service.py tests/services/test_trace_analyzer_service.py` -> 4 passed (2026-03-06).

---

## Section 20: Run comparison and improvement metrics (boosting)

**Depends on:** Sections 3 (sandbox), 9 (run_command). Optional: Section 19 if orchestration triggers metrics.

**Single goal:** After the tracer suggests changes and (optionally) applies them in the sandbox, run the target agent or its tests and compare outcome to baseline to measure improvement (boosting).

**Deep-agent capability:** Boosting / improvement measurement — baseline vs post-change metrics (e.g. tests_passed_before/after, delta); harness improvement signal.

**Details:**
- **Deep-agent approach:** Implements **boosting** (per [article](https://blog.langchain.com/improving-deep-agents-with-harness-engineering/)): measure improvement from harness changes by comparing baseline vs post-change outcomes. Uses the same sandbox/code-execution backend (Section 3, Section 9) to run target agent or tests; output is the harness improvement signal for human or downstream use.
- Baseline: run target agent (or test suite) before harness changes; record pass/fail or score.
- After changes: run again in same sandbox (or new sandbox with same repo + changes); record pass/fail or score.
- Output: before/after metrics (e.g. tests_passed_before, tests_passed_after, delta). No automatic “apply to production” in this section.
- Optionally: run only the test suite of the target repo if full agent run is expensive.

**Tech stack and dependencies**
- Sandbox (Section 3) and run-command tool (Section 9); optional: store metrics in DB (extend schema if needed).

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/services/improvement_metrics_service.py | Run baseline and post-change, compute delta. |
| src/backend/schemas/improvement_metrics.py | Pydantic models for before/after metrics. |
| src/backend/routers/tracer.py | Optional: extend response or add GET /api/tracer/run/:id/metrics (when Section 21 adds API). |

**How to test:** Unit test: given two mock run outputs (pass/fail counts), assert delta. Integration: run tracer, apply one change, run tests twice, assert metrics structure.

**Test results:** (Add when section is complete.)

---

## Section 21: API endpoint – trigger tracer run

**Depends on:** Section 19 (orchestration service), Section 3 (default target repo from config).

**Single goal:** Expose a FastAPI endpoint to trigger the tracer on a given Langfuse run (or trace set) and target repo path.

**Deep-agent capability:** Orchestration entry — API to trigger full tracer flow (fetch → sandbox → tracer → harness suggestions); default target repo from config when URL omitted.

**Details:**
- **Deep-agent approach:** API is the single entry point to run the **full deep-agent tracer**: call trace analyzer service (Section 19), return harness change output. If using `create_deep_agent`, this endpoint invokes that graph with tracer tools and middleware; same contract either way.
- Input: run_id (or trace_ids), target_repo_url or path (optional), optional time/step budget.
- **Configure tracer to target repo:** If `target_repo_url` is omitted, use configured default from env `TRACER_DEFAULT_TARGET_REPO_URL` (Section 3; default `https://github.com/Nickbohm555/agent-search`).
- Flow: call trace_analyzer_service (fetch traces, create sandbox, invoke LangGraph tracer, return harness change suggestions); optionally include improvement metrics (Section 20). Return harness change suggestions (Section 17–18) and optionally final state.
- Endpoint is async; long runs may need background task or job ID (document choice).

**Tech stack and dependencies**
- FastAPI router; depends on trace_analyzer_service (Section 19).

**Files and purpose**

| File | Purpose |
|------|--------|
| src/backend/routers/tracer.py | POST /api/tracer/run or similar; call trace_analyzer_service. |
| src/backend/main.py | Include tracer router. |
| src/backend/schemas/tracer_api.py | Request/response models for the endpoint. |

**How to test:** Integration test: call endpoint with mock run_id and repo; assert 200 and response contains suggestions or state (mock Langfuse/sandbox if needed).

**Test results:** (Add when section is complete.)

---

## Section 22: UI – Tracer run form and job status

**Depends on:** Section 21 (API).

**Single goal:** Provide a UI to trigger a tracer run and (if the API is async) show job status and completion.

**Deep-agent capability:** Human-in-the-loop / operator interface — trigger run (run_id, repo, budget), submit to API, poll job status and completion.

**Details:**
- **Deep-agent approach:** Harness [human-in-the-loop](https://docs.langchain.com/oss/python/deepagents/harness#human-in-the-loop) / operator interface: user triggers a tracer run (run_id, repo, budget), submits to API, and polls for job status and completion.
- Form: run_id (or trace_ids), target_repo_url (or path), optional time/step budget, optional LANGFUSE_* overrides (e.g. project/env).
- Submit calls POST /api/tracer/run (or equivalent). If the backend uses a job queue or background task, support job_id and poll GET /api/tracer/run/:id or /api/tracer/jobs/:id for status and result.
- Show clear errors (e.g. invalid run_id, clone failure) and success state (e.g. “Run started” or “Run completed” with link to results).

**Tech stack and dependencies**
- Existing frontend (e.g. React/Vite in `src/frontend`); use existing `api` and routing patterns.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/frontend/src/... (e.g. pages/TracerRun.tsx or similar) | Form component: inputs, submit, job status polling. |
| src/frontend/src/... (e.g. api.ts or tracerApi.ts) | API client for POST /api/tracer/run and GET run/job status. |
| src/frontend/src/App.tsx (or router) | Route to tracer run UI. |

**How to test:** Manual or E2E: submit form with mock run_id and repo; assert request shape and (if async) status updates. Optionally mock backend.

**Test results:** (Add when section is complete.)

---

## Section 23: UI – Harness change results and metrics

**Depends on:** Sections 17 (harness change schema), 21 (API and run flow), optionally 20 (metrics).

**Single goal:** Display the tracer output: suggested harness changes and (if available) before/after improvement metrics.

**Deep-agent capability:** Human-in-the-loop / visibility — display harness change list and optional before/after metrics for review and approval.

**Details:**
- **Deep-agent approach:** Harness human-in-the-loop **visibility**: display the tracer’s harness change output and optional boosting metrics so humans can review, approve, or reject before applying. Read-only in this section; data from run result or GET /api/tracer/run/:id (and optionally GET .../metrics).
- After a run completes (or when opening a completed run), show: list of suggested changes (prompt edits, tool changes, config) in a readable format; optional before/after metrics (e.g. tests_passed_before/after, delta) from Section 20.
- Data comes from the run result or GET /api/tracer/run/:id (and optionally GET .../metrics). No editing of suggestions in this section; display only.

**Tech stack and dependencies**
- Same frontend stack; depends on Section 21 (API and run flow), optionally Section 20 (metrics).

**Files and purpose**

| File | Purpose |
|------|--------|
| src/frontend/src/... (e.g. TracerResults.tsx or HarnessChanges.tsx) | Display harness change list and optional metrics. |
| src/frontend/src/... (api) | GET run result or metrics if separate endpoint. |

**How to test:** Render component with mock harness changes and metrics; assert structure and labels. Optional: wire to real run result.

**Test results:** (Add when section is complete.)

---
