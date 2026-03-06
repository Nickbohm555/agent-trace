# Agent-Trace Implementation Plan

Tasks are in **recommended implementation order** (1…n). Each section = **one context window**.  
Refactor existing implementation into a **deep-agent library in LangGraph**. Sections are atomic (one deliverable each).

**Current section to work on:** Section 1.

---

## Section 1: Deep-agent library package layout and dependency surface

**Single goal:** Define the Python package layout and LangGraph dependency boundary for the deep-agent tracer library so the rest of the refactor has a single target.

**Details:**
- Create a dedicated library package (e.g. `src/backend/agents/deep_agent` or top-level `agent_trace_lib`) with `__init__.py` and clear public exports.
- Declare and pin LangGraph (and langchain-core, langchain-openai) as the library’s only graph/runtime dependencies; no FastAPI, DB, or app-specific imports inside the library core.
- Document which modules are “library” vs “app” (backend services, routers, DB) so dependencies point inward (app → library).

**Tech stack and dependencies**
- Python package layout (e.g. `src/backend/agents/deep_agent/` or `agent_trace_lib/`); `pyproject.toml` optional if library lives inside backend tree.
- LangGraph, langchain-core, langchain-openai already in `src/backend/pyproject.toml`; no new packages for this section.

**Files and purpose**

| File | Purpose |
|------|---------|
| New: `src/backend/agents/deep_agent/__init__.py` (or chosen root) | Package root and public API surface (e.g. `create_tracer_graph`, `TracerState`). |
| New: `src/backend/agents/deep_agent/README.md` or docstring | Document library boundary and dependency rule (library does not import app/DB/FastAPI). |

**How to test:** No code movement yet. Verify package is importable (`from agents.deep_agent import ...` or equivalent) and that no app/DB imports exist inside the new package.

**Test results:** (Add when section is complete.)

---

## Section 2: Move tracer state schema into the deep-agent library

**Single goal:** Relocate tracer graph state (messages, run_id, sandbox_path, reasoning, time budget, loop detection, parallel findings, harness output) into the library so the graph is library-owned.

**Details:**
- Move `tracer_state.py` (or equivalent state TypedDict/dataclass) into the library package.
- State must remain compatible with LangGraph `StateGraph` and existing node signatures; no behavioral change, only location and imports.
- Backend and any callers import state type from the library.

**Tech stack and dependencies**
- LangGraph state typing (TypedDict or annotated dict); no new dependencies.

**Files and purpose**

| File | Purpose |
|------|---------|
| New: `src/backend/agents/deep_agent/state.py` | Tracer graph state definition (messages, run_id, sandbox_path, reasoning_*, time_budget_*, edit_file_counts, parallel_error_*, harness_change_*, etc.). |
| Delete or redirect: `src/backend/agents/tracer_state.py` | Remove or re-export from library so existing imports are updated to library. |

**How to test:** Unit test that state shape is unchanged; graph construction and one invoke still work when state is imported from the library.

**Test results:** (Add when section is complete.)

---

## Section 3: Move tracer reasoning config into the deep-agent library

**Single goal:** Relocate phase-aware reasoning budget configuration (planning, implementation, verification; reasoning sandwich) into the library so the graph uses library-owned config.

**Details:**
- Move `tracer_config.py` (reasoning levels, phase mapping, `from_run_config`) into the library.
- No change to behavior or defaults; only module location and import paths.
- Graph and app resolve config from the library.

**Tech stack and dependencies**
- No new dependencies.

**Files and purpose**

| File | Purpose |
|------|---------|
| New: `src/backend/agents/deep_agent/config.py` | Reasoning phase/level and run-config parsing. |
| Delete or redirect: `src/backend/agents/tracer_config.py` | Remove or re-export from library; update all imports. |

**How to test:** Existing tracer_config tests run against library module; graph still receives correct reasoning budget per phase.

**Test results:** (Add when section is complete.)

---

## Section 4: Move tracer graph backbone into the deep-agent library

**Single goal:** Relocate the LangGraph StateGraph (entry, agent node, conditional edges, tools route, verify route, END) into the library so the tracer graph is built and compiled inside the library.

**Details:**
- Move graph construction (add_node, add_edge, add_conditional_edge) and compile into the library; expose a factory such as `create_tracer_graph(tool_builders, middleware_config, ...)`.
- Agent node and conditional routing (continue vs verify vs END) live in the library; tool binding remains injectable via callables or tool lists passed from the app.
- No tools or middleware implementations moved yet—only the backbone and wiring points for tools/middleware.

**Tech stack and dependencies**
- LangGraph, langchain-core; already in use.

**Files and purpose**

| File | Purpose |
|------|---------|
| New: `src/backend/agents/deep_agent/graph.py` | Build and compile StateGraph; expose `create_tracer_graph(...)` with hooks for tools and middleware. |
| Delete or redirect: graph logic in `src/backend/agents/langgraph_agent.py` | Remove graph build from app; app imports and invokes library graph. |

**How to test:** Integration test: create graph from library with minimal/no tools, run one step, assert state and route behavior unchanged.

**Test results:** (Add when section is complete.)

---

## Section 5: Move trace read tool into the deep-agent library

**Single goal:** Relocate the read_trace tool (and its dependency contract) into the library so trace observation is a library-provided tool.

**Details:**
- Move tool implementation into the library; storage/read is behind an abstract interface (e.g. “trace storage adapter”) that the app implements and injects.
- Library exposes a tool builder (e.g. `build_read_trace_tool(adapter)`) that the graph factory can bind.
- No change to tool input/output schema or behavior.

**Tech stack and dependencies**
- Library depends only on the adapter interface (protocol or ABC); app provides concrete TraceStorageService (or equivalent).

**Files and purpose**

| File | Purpose |
|------|---------|
| New: `src/backend/agents/deep_agent/tools/trace.py` | read_trace tool and adapter protocol. |
| Delete or redirect: `src/backend/tools/trace_tools.py` | Remove or re-export from library; app wires adapter into library tool builder. |

**How to test:** Unit test tool with mock adapter; integration test graph with read_trace bound and storage adapter from app.

**Test results:** (Add when section is complete.)

---

## Section 6: Move codebase tools (list, read, edit) into the deep-agent library

**Single goal:** Relocate list_directory, read_file, and edit_file tools into the library with a sandbox adapter interface so the graph uses library-owned codebase tools.

**Details:**
- Move tool implementations into the library; filesystem access is behind a sandbox adapter (e.g. list_dir, read_file, write_file) that the app implements and injects.
- Library exposes tool builders that the graph factory can bind.
- No change to tool schemas or behavior.

**Tech stack and dependencies**
- Adapter interface only; app provides SandboxService-backed implementation.

**Files and purpose**

| File | Purpose |
|------|---------|
| New: `src/backend/agents/deep_agent/tools/codebase.py` | list_directory, read_file, edit_file and sandbox adapter protocol. |
| Delete or redirect: `src/backend/tools/codebase_tools.py` | Remove or re-export from library; app wires sandbox into library tool builders. |

**How to test:** Unit tests with mock sandbox adapter; integration test graph with codebase tools bound.

**Test results:** (Add when section is complete.)

---

## Section 7: Move run-command tool into the deep-agent library

**Single goal:** Relocate the run_command (sandbox) tool into the library behind a sandbox adapter so the graph uses a library-owned execution tool.

**Details:**
- Move run_command implementation into the library; execution is behind the same or extended sandbox adapter (run_command method).
- Library exposes tool builder for run_command; graph factory binds it when sandbox adapter is provided.
- No change to tool schema or behavior.

**Tech stack and dependencies**
- Same sandbox adapter as Section 6; no new dependencies.

**Files and purpose**

| File | Purpose |
|------|---------|
| New: `src/backend/agents/deep_agent/tools/execution.py` | run_command tool and adapter extension for command execution. |
| Delete or redirect: `src/backend/tools/sandbox_tools.py` | Remove or re-export from library; app wires sandbox into library. |

**How to test:** Unit test with mock adapter; integration test graph with run_command bound.

**Test results:** (Add when section is complete.)

---

## Section 8: Move tracer system prompts into the deep-agent library

**Single goal:** Relocate the tracer system prompt (plan–build–verify–fix and testable-code expectations) into the library so the graph injects library-owned prompt text.

**Details:**
- Move prompt builder (full system prompt + testable-code fragment) into the library.
- Graph or agent node calls library to get system message(s); no app-specific prompt logic in the graph.
- No change to prompt content or structure.

**Tech stack and dependencies**
- No new dependencies.

**Files and purpose**

| File | Purpose |
|------|---------|
| New: `src/backend/agents/deep_agent/prompts.py` | System prompt builder and testable-code fragment. |
| Delete or redirect: `src/backend/agents/tracer_prompts.py` | Remove or re-export from library; update graph to use library prompts. |

**How to test:** Prompt tests assert same content and markers; graph test asserts system message present in model input.

**Test results:** (Add when section is complete.)

---

## Section 9: Move local context injection into the deep-agent library

**Single goal:** Relocate sandbox local context discovery and injection (cwd, directory map, tool paths) into the library so the graph injects library-owned context.

**Details:**
- Move context builder and injection logic into the library; sandbox info is provided via the same sandbox adapter (or a context callback) that the app injects.
- First-turn system message for local context is built and appended inside the library.
- No change to context shape or behavior.

**Tech stack and dependencies**
- Sandbox adapter (or context provider) interface; no new packages.

**Files and purpose**

| File | Purpose |
|------|---------|
| New: `src/backend/agents/deep_agent/context.py` | Local context builder and injection hook. |
| Delete or redirect: `src/backend/agents/tracer_context.py` | Remove or re-export from library; graph uses library context. |

**How to test:** Unit test context output shape; integration test that first turn includes local context in state.

**Test results:** (Add when section is complete.)

---

## Section 10: Move pre-completion verification middleware into the deep-agent library

**Single goal:** Relocate the pre-completion checklist (Ralph Wiggum–style “did you run tests?”) into the library so the graph routes through library-owned middleware before END.

**Details:**
- Move `should_inject_pre_completion_checklist`, `build_pre_completion_checklist_message`, and `pre_completion_check` node logic into the library.
- Graph backbone wires verify route and pre_completion node from the library; state field `pre_completion_verified` lives in library state.
- No change to checklist content or routing behavior.

**Tech stack and dependencies**
- No new dependencies.

**Files and purpose**

| File | Purpose |
|------|---------|
| New: `src/backend/agents/deep_agent/middleware/pre_completion.py` | Pre-completion check detection, message builder, and node. |
| Delete or redirect: pre-completion parts of `src/backend/agents/tracer_middleware.py` | Remove or re-export from library; graph uses library middleware. |

**How to test:** Middleware unit tests; graph test that verify route runs and one-more-turn behavior is unchanged.

**Test results:** (Add when section is complete.)

---

## Section 11: Move time-budget injection middleware into the deep-agent library

**Single goal:** Relocate time/step-remaining injection (warnings and nudge toward verify/submit) into the library so the graph uses library-owned time-budget middleware.

**Details:**
- Move `apply_time_budget_injection`, `build_time_budget_message`, and state updates (step count, last notice step) into the library.
- Graph invokes library middleware before model invocation; state fields for time budget live in library state.
- No change to trigger intervals or message content.

**Tech stack and dependencies**
- No new dependencies.

**Files and purpose**

| File | Purpose |
|------|---------|
| New: `src/backend/agents/deep_agent/middleware/time_budget.py` | Time-budget state updates and message builder; hook called from agent node. |
| Delete or redirect: time-budget parts of `src/backend/agents/tracer_middleware.py` | Remove or re-export from library; graph uses library middleware. |

**How to test:** Unit test budget message and triggers; graph test with max_steps=1 asserts budget message in state.

**Test results:** (Add when section is complete.)

---

## Section 12: Move loop-detection middleware into the deep-agent library

**Single goal:** Relocate per-file edit counting and “reconsider your approach” nudge into the library so the graph uses library-owned loop-detection middleware.

**Details:**
- Move `apply_loop_detection_injection`, `build_loop_detection_message`, and state updates (edit_file_counts, loop_detection_nudged_files) into the library.
- Graph invokes library middleware on model response; state fields live in library state.
- No change to threshold or message content.

**Tech stack and dependencies**
- No new dependencies.

**Files and purpose**

| File | Purpose |
|------|---------|
| New: `src/backend/agents/deep_agent/middleware/loop_detection.py` | Loop-detection state updates and nudge message; hook called from graph. |
| Delete or redirect: loop-detection parts of `src/backend/agents/tracer_middleware.py` | Remove or re-export from library; graph uses library middleware. |

**How to test:** Unit test threshold and nudge; graph test with repeated edit_file asserts nudge injected.

**Test results:** (Add when section is complete.)

---

## Section 13: Move error-analysis subagent into the deep-agent library

**Single goal:** Relocate parallel error-analysis (collect_error_tasks, analyze_errors_in_parallel, ErrorAnalysisFinding) into the library so the tracer uses a library-owned subagent.

**Details:**
- Move error collection and parallel analysis logic into the library; trace input is provided via an adapter or in-memory trace list that the app supplies.
- Library exposes a function or small subgraph that the main graph calls; findings are written into library state.
- No change to finding shape or concurrency behavior.

**Tech stack and dependencies**
- asyncio/sync already used; no new dependencies.

**Files and purpose**

| File | Purpose |
|------|---------|
| New: `src/backend/agents/deep_agent/subagents/error_analysis.py` | collect_error_tasks, analyze_errors_in_parallel, ErrorAnalysisFinding. |
| Delete or redirect: `src/backend/agents/error_analysis_agent.py` | Remove or re-export from library; graph invokes library subagent. |

**How to test:** Unit test task collection and parallel run; integration test graph with persisted traces asserts findings in state.

**Test results:** (Add when section is complete.)

---

## Section 14: Move harness change schema into the deep-agent library

**Single goal:** Relocate the machine-readable harness change schema (SuggestedPromptEdit, SuggestedToolChange, SuggestedConfigChange, HarnessChange, HarnessChangeSet) into the library so synthesis and API both use library-owned types.

**Details:**
- Move Pydantic models and validators into the library; library is the single source of truth for harness change structure.
- Backend schemas (API) and synthesis output import or re-export from the library.
- No change to validation rules or JSON shape.

**Tech stack and dependencies**
- Pydantic; already in use.

**Files and purpose**

| File | Purpose |
|------|---------|
| New: `src/backend/agents/deep_agent/schemas/harness_changes.py` | Harness change models and HarnessChangeSet. |
| Delete or redirect: `src/backend/schemas/harness_changes.py` | Remove or re-export from library; API and synthesis use library types. |

**How to test:** Existing harness_change schema tests run against library module; API/synthesis tests still pass.

**Test results:** (Add when section is complete.)

---

## Section 15: Move synthesis (harness change output) into the deep-agent library

**Single goal:** Relocate the step that converts parallel_error_findings into HarnessChangeSet into the library so the main tracer produces library-owned structured output.

**Details:**
- Move `_synthesize_harness_changes` (or equivalent) into the library; input is findings in state, output is HarnessChangeSet written to library state.
- Graph invokes library synthesis after error analysis; no synthesis logic in the app.
- No change to mapping from findings to change categories or confidence.

**Tech stack and dependencies**
- Library harness change schema (Section 14); no new dependencies.

**Files and purpose**

| File | Purpose |
|------|---------|
| New: `src/backend/agents/deep_agent/synthesis.py` | synthesize_harness_changes(findings) -> HarnessChangeSet; used by graph. |
| Delete or redirect: synthesis logic in `src/backend/agents/langgraph_agent.py` | Remove or call library from graph. |

**How to test:** Unit test synthesis output shape; graph test asserts harness_change_set in final state.

**Test results:** (Add when section is complete.)

---

## Section 16: Move trace-analyzer orchestration into the deep-agent library

**Single goal:** Relocate the full flow (fetch traces → store/load → create sandbox → run tracer graph → synthesize → teardown) into a single library entry point so the app only calls the library.

**Details:**
- Move orchestration logic into the library; fetch/storage/sandbox are behind adapters (Langfuse client, trace storage, sandbox factory) that the app implements and injects.
- Library exposes one entry point (e.g. `run_trace_analyzer(request, adapters)`) returning harness change set and optional final state.
- No change to flow order or behavior; only location and dependency injection.

**Tech stack and dependencies**
- Library uses graph factory, synthesis, and adapters; no FastAPI or DB inside library.

**Files and purpose**

| File | Purpose |
|------|---------|
| New: `src/backend/agents/deep_agent/orchestration.py` | run_trace_analyzer(request, adapters); fetch, store, sandbox, invoke graph, synthesize, teardown. |
| Delete or redirect: `src/backend/services/trace_analyzer_service.py` | Remove or thin wrapper that builds adapters and calls library. |

**How to test:** Integration test with mocked adapters asserts call order and return shape; existing e2e test (if any) still passes via app wrapper.

**Test results:** (Add when section is complete.)

---

## Section 17: Wire improvement-metrics (baseline/post) into library orchestration

**Single goal:** Add optional improvement-metrics (baseline run, post-change run, delta) to the library orchestration so boosting is a library feature with an app-provided evaluation adapter.

**Details:**
- Library orchestration accepts an optional “evaluation” adapter: run_baseline(), run_after_change(), parse metrics.
- Between baseline and post-change, orchestration runs the tracer graph (and optionally applies suggested changes via another callback); then runs post-change evaluation and computes delta.
- ImprovementMetrics (or equivalent) is defined in the library or in a shared schema used by the library; app implements the evaluation adapter.

**Tech stack and dependencies**
- No new dependencies; optional adapter interface.

**Files and purpose**

| File | Purpose |
|------|---------|
| `src/backend/agents/deep_agent/orchestration.py` | Extend run_trace_analyzer to accept optional evaluation adapter and return improvement_metrics. |
| New or existing: `src/backend/agents/deep_agent/schemas/improvement_metrics.py` | ImprovementDelta, EvaluationRunMetrics, ImprovementMetrics (if moved into library). |

**How to test:** Unit test delta computation; integration test with mock evaluation adapter asserts baseline → graph → post-change order and metrics in result.

**Test results:** (Add when section is complete.)

---

## Section 18: Refactor backend to depend on deep-agent library only for tracer

**Single goal:** Ensure the backend uses the deep-agent library as the only implementation of the tracer graph and orchestration; no duplicate graph or orchestration logic in the app.

**Details:**
- Backend imports graph factory, orchestration, and types from the library; builds adapters (TraceStorageService, SandboxService, LangfuseTraceService) and passes them into the library.
- Remove any remaining graph/orchestration code from `langgraph_agent.py` or equivalent; that module becomes a thin wrapper or is removed in favor of direct library use.
- All tracer tests that assert graph/orchestration behavior run against the library or the app’s use of it.

**Tech stack and dependencies**
- Backend pyproject.toml depends on same repo “library” package (path or editable install); no new external deps.

**Files and purpose**

| File | Purpose |
|------|---------|
| `src/backend/agents/langgraph_agent.py` or `src/backend/services/trace_analyzer_service.py` | Thin wrapper: build adapters, call library create_tracer_graph / run_trace_analyzer. |
| `src/backend/main.py` | No change to routes; dependency injection provides service that uses library. |

**How to test:** Full backend test suite (tracer + API); restart app and run one tracer run via API to confirm no regressions.

**Test results:** (Add when section is complete.)

---

## Section 19: Ensure API endpoint uses library orchestration only

**Single goal:** Verify the tracer run API (POST /api/tracer/run) invokes only the library orchestration entry point and returns library-defined result shape.

**Details:**
- Router calls a backend service that in turn calls library `run_trace_analyzer` (or equivalent); no inline graph or orchestration logic in the router.
- Request/response schemas align with library types (run_id, trace_ids, harness_change_set, improvement_metrics); map library result to API response.
- Document that long runs may require background task or job ID (no implementation change required in this section).

**Tech stack and dependencies**
- FastAPI, existing router; no new dependencies.

**Files and purpose**

| File | Purpose |
|------|---------|
| `src/backend/routers/tracer.py` | Call service that uses library; map errors and result to HTTP. |
| `src/backend/schemas/tracer_api.py` | Request/response models; align with library TraceAnalyzerRequest/Result if applicable. |

**How to test:** API integration test: POST with run_id, assert 200 and response shape; assert no duplicate graph/orchestration code in router.

**Test results:** (Add when section is complete.)

---

## Section 20: Verify UI against refactored API

**Single goal:** Confirm the existing UI (tracer run form, job status, harness change results, metrics) works unchanged against the refactored backend and library.

**Details:**
- No UI code change required unless API response shape or error format changed; if changed, update frontend types and rendering only as needed.
- Manually or via E2E: submit run, poll or wait for completion, check harness change list and optional metrics display.
- Document any small frontend fixes (e.g. field renames) in this section.

**Tech stack and dependencies**
- Frontend already in place; no new dependencies unless response shape changed.

**Files and purpose**

| File | Purpose |
|------|---------|
| `src/frontend/src/utils/api.ts` | Adjust types if library/API response shape changed. |
| `src/frontend/src/App.tsx` | Adjust rendering only if response shape or error format changed. |

**How to test:** Frontend unit tests; manual or E2E: trigger run, verify success and result display.

**Test results:** (Add when section is complete.)

---
