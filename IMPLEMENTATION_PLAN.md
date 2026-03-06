# Agent-Trace Implementation Plan

Tasks are in **recommended implementation order** (1…n). Each section = **one context window**. Sections are atomic (one deliverable each).

**Current section to work on:** Section E7

---

## E2E test sections (concrete, atomic)

The following sections are **one section = one E2E test**. Use AGENTS.md for Docker and Chrome DevTools workflow (e.g. `docker compose up -d backend frontend`, `docker compose stop chrome`, `./launch-devtools.sh http://localhost:5174`, `curl http://127.0.0.1:9223/json/list`). Ports: backend=8001, frontend=5174, chrome debug=9223. Before marking any E2E section complete: restart the app after code changes, check logs, run the test steps; if anything fails, fix and repeat. Only then record **Test results** and consider the section complete.

**Frontend-mocked E2E:** Sections E6–E14 run in the frontend test suite with **mocked `fetch`** (Vitest `vi.stubGlobal("fetch", ...)`). No real backend or LLM is required; the tests assert that the full UI flow (form → request → result/error display) works for each scenario. Run with `docker compose exec frontend npm run test` (or from repo root: frontend in Docker or local `npm run test`). This gives fast, deterministic coverage that "the whole thing works" from the user's perspective.

---

## Section E1: E2E — Services start and health endpoint returns 200

**Single goal:** Verify that after `docker compose up -d`, backend (and db/frontend) are up and `GET /api/health` returns 200 with expected body.

**Details:**
- Start stack: `docker compose up -d` (or `backend frontend` and `db` as needed). Optionally `docker compose build` first if dependencies changed.
- Assert: `curl -s -o /dev/null -w '%{http_code}' http://localhost:8001/api/health` equals `200`.
- Assert: response body contains `"status":"ok"` (or equivalent per backend contract).
- No browser or Chrome DevTools required; curl-only.

**Tech stack and dependencies**
- Docker Compose, curl. No new packages.

**Files and purpose**

| File | Purpose |
|------|--------|
| (none) | No code changes; verification only. |

**How to test:** From project root: `docker compose up -d backend frontend db`; wait for healthy; `curl -s http://localhost:8001/api/health`; assert status 200 and body. Run `docker compose ps` and confirm backend (and frontend, db) Up.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section E2: E2E — Frontend loads at configured URL

**Single goal:** Verify the frontend is reachable at the configured URL and returns a non-error page.

**Details:**
- With backend/frontend (and db) running, request the frontend root at `http://localhost:5174` (per AGENTS.md).
- Assert: HTTP 200 and response is HTML (or acceptable SPA payload).
- No browser automation required; curl or similar is enough for this atomic check.

**Tech stack and dependencies**
- Docker Compose, curl. No new packages.

**Files and purpose**

| File | Purpose |
|------|--------|
| (none) | Verification only. |

**How to test:** `docker compose up -d backend frontend`; `curl -s -o /dev/null -w '%{http_code}' http://localhost:5174`; assert 200. Optionally assert response contains expected root element or title.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section E3: E2E — POST /api/tracer/run returns 200 and response shape

**Single goal:** Verify that a valid `POST /api/tracer/run` returns 200 and a response body that matches the API contract (e.g. harness_change_set, improvement_metrics).

**Details:**
- Send `POST /api/tracer/run` with `Content-Type: application/json` and body including at least `run_id` (e.g. `{"run_id":"e2e-run-1","limit":1,"max_runtime_seconds":30,"max_steps":1}`).
- Assert: status 200.
- Assert: JSON response has required keys (e.g. `harness_change_set`; optionally `improvement_metrics`). Do not assert exact content; only shape and presence.
- Run against live backend (Docker); no mocks.

**Tech stack and dependencies**
- Docker Compose, curl. No new packages.

**Files and purpose**

| File | Purpose |
|------|--------|
| (none) | Verification only; optional: add or extend API test that runs against TestClient with real service if desired. |

**How to test:** Backend running; `curl -s -X POST http://localhost:8001/api/tracer/run -H 'Content-Type: application/json' -d '{"run_id":"e2e-run-1","limit":1,"max_runtime_seconds":30,"max_steps":1}'`; assert 200; parse JSON and assert key `harness_change_set` exists.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section E4: E2E — API validation error returns 422 and detail shape

**Single goal:** Verify that an invalid request to `POST /api/tracer/run` (e.g. missing both `run_id` and `trace_ids`) returns 422 and a `detail` field suitable for UI error display.

**Details:**
- Send `POST /api/tracer/run` with body missing required identifiers (e.g. `{}` or `{"target_repo_url":"https://example.com/repo.git"}` only).
- Assert: status 422.
- Assert: response has `detail` (string or array of validation errors). No change to backend schema required unless contract is undocumented.
- Ensures API and frontend error handling have a consistent contract.

**Tech stack and dependencies**
- Docker Compose, curl. No new packages.

**Files and purpose**

| File | Purpose |
|------|--------|
| (none) | Verification only. |

**How to test:** Backend running; `curl -s -X POST http://localhost:8001/api/tracer/run -H 'Content-Type: application/json' -d '{"target_repo_url":"https://example.com/repo.git"}'`; assert 422; assert JSON has `detail`.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section E5: E2E — Chrome DevTools debug endpoint reachable

**Single goal:** Verify the Chrome DevTools workflow from AGENTS.md: after stopping Docker Chrome (if any) and launching local Chrome via `launch-devtools.sh`, the debug endpoint returns targets.

**Details:**
- Per AGENTS.md: `docker compose stop chrome` if chrome service exists; then `./launch-devtools.sh http://localhost:5174` to start a local Chrome with DevTools.
- Assert: `curl http://127.0.0.1:9223/json/list` returns JSON with at least one target and `webSocketDebuggerUrl` (agent-trace uses port 9223).
- If port 9223 is already in use and returns targets, reuse that session (document in test results).
- This section validates the E2E browser-testing setup only; no UI assertions.

**Tech stack and dependencies**
- Local Chrome, launch-devtools.sh, curl. No new packages in repo.

**Files and purpose**

| File | Purpose |
|------|--------|
| (none) | Verification only. |

**How to test:** From project root: `docker compose stop chrome` (if present); `./launch-devtools.sh http://localhost:5174`; `curl -s http://127.0.0.1:9223/json/list`; assert valid JSON with targets and webSocketDebuggerUrl.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section E6: E2E (mocked) — Form validation and submit guard

**Single goal:** With mocked fetch, verify the form disables submit when neither Run ID nor Trace IDs are provided and shows the hint; submit is enabled when at least one is provided.

**Details:**
- Render App; assert "Run Tracer" button is disabled when both run_id and trace_ids inputs are empty.
- Assert hint text "Provide `Run ID` or at least one `Trace ID`" is visible when canSubmit is false.
- Fill Run ID (or Trace IDs); assert button becomes enabled. No fetch mock needed for disabled state; optional mock for submit to avoid unhandled promise.
- All assertions via React Testing Library (screen.getByRole, getByLabelText, getByText).

**Tech stack and dependencies**
- Vitest, @testing-library/react. No new packages; existing frontend test setup.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/frontend/src/App.test.tsx | Add test: form validation and submit guard. |

**How to test:** `docker compose exec frontend npm run test` (or `npm run test` in src/frontend). Assert disabled state and hint; assert enabled after filling run_id or trace_ids.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section E7: E2E (mocked) — Submit with run_id only, success response shows summary and changes

**Single goal:** With fetch mocked to return 200 and a valid TracerRunResponse (harness_change_set with at least one change), submit form with only Run ID filled; assert Completed, summary text, and at least one harness change title visible.

**Details:**
- Mock fetch to resolve with ok: true and JSON matching TracerRunResponse (run_id, harness_change_set.summary, harness_changes with title).
- Render App; fill "Run ID" only; click "Run Tracer". Assert fetch called with POST to /api/tracer/run and body includes run_id.
- Assert "Completed" in Job Status; assert harness_change_set.summary text on page; assert first change title visible. Covers the main happy path from frontend only.

**Tech stack and dependencies**
- Vitest, @testing-library/react. Existing setup; mock matches api.ts TracerRunResponse.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/frontend/src/App.test.tsx | Add or extend test: run_id-only submit, success, summary + change list visible. |

**How to test:** `npm run test` in frontend; test may already exist (e.g. "submits run payload and renders completion summary"); extend or duplicate for run_id-only if needed.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section E8: E2E (mocked) — Submit with trace_ids only, success response

**Single goal:** With fetch mocked for 200, submit form with only Trace IDs (comma-separated) filled; assert request body includes trace_ids array and UI shows Completed with result.

**Details:**
- Mock fetch for success response (same shape as E7).
- Fill "Trace IDs (comma-separated)" with e.g. "trace-a, trace-b"; leave Run ID empty. Submit.
- Assert fetch body has trace_ids: ["trace-a", "trace-b"] and no run_id (or run_id undefined). Assert "Completed" and result section visible. Ensures trace_ids-only path works.

**Tech stack and dependencies**
- Vitest, @testing-library/react. No new packages.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/frontend/src/App.test.tsx | Add test: trace_ids-only submit, request shape and success UI. |

**How to test:** `npm run test`; assert request payload and Completed + result.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section E9: E2E (mocked) — Success with empty harness changes

**Single goal:** Mock 200 with harness_change_set.harness_changes.length === 0 and summary like "No harness changes were synthesized." Assert UI shows "No harness changes were returned by this run." and no Improvement Metrics section.

**Details:**
- Mock response: harness_changes: [], summary: "No harness changes were synthesized by the tracer graph." (or equivalent), improvement_metrics: null.
- Submit form; assert Completed; assert the empty-state hint text is visible; assert no "Improvement Metrics" heading. Ensures empty-result path does not break and matches backend contract.

**Tech stack and dependencies**
- Vitest, @testing-library/react. No new packages.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/frontend/src/App.test.tsx | Add test: empty harness changes and no metrics. |

**How to test:** `npm run test`; assert empty-state message and no metrics section.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section E10: E2E (mocked) — Running state while request in flight

**Single goal:** Mock fetch with a promise that resolves after a short delay. After clicking Run Tracer, assert button text is "Running..." and Job Status shows "Running" before resolution; after resolution, assert "Completed" and "Run Tracer" again.

**Details:**
- Use vi.fn() that returns a Promise resolving after e.g. 50ms with success JSON. Click submit; immediately assert "Running..." and "Running". await waitFor for "Completed" and summary. Ensures loading state is visible and clears on success.

**Tech stack and dependencies**
- Vitest, @testing-library/react. No new packages.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/frontend/src/App.test.tsx | Add test: running state during request, then completed. |

**How to test:** `npm run test`; assert Running state then Completed.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section E11: E2E (mocked) — 422 validation error shows parsed message

**Single goal:** Mock fetch for 422 with body.detail as array of objects (e.g. msg: "Value error, Provide at least one of run_id or trace_ids."). Assert Job Status "Failed" and the parsed error message is visible in the UI.

**Details:**
- Same as existing test "renders backend error message when run fails": mock ok: false, status: 422, json with detail array. Assert "Failed" and the extracted message text. Ensures frontend parseErrorMessage (array detail) is covered and UI shows it.

**Tech stack and dependencies**
- Vitest, @testing-library/react. No new packages; test may already exist.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/frontend/src/App.test.tsx | Retain or add test: 422 array detail → Failed + message. |

**How to test:** `npm run test`; assert Failed and error message text.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section E12: E2E (mocked) — Network or 5xx error shows generic message

**Single goal:** Mock fetch to resolve with ok: false and no JSON or non-JSON body (or status 500). Assert Job Status "Failed" and that a non-empty error message is shown (fallback from parseErrorMessage).

**Details:**
- Mock: ok: false, status: 500, json: async () => ({ detail: "Internal server error" }) or throw. Assert "Failed" and that screen has an error paragraph with content. Ensures error path does not leave UI blank.

**Tech stack and dependencies**
- Vitest, @testing-library/react. No new packages.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/frontend/src/App.test.tsx | Add test: 5xx or network-style error, error message visible. |

**How to test:** `npm run test`; assert Failed and error message present.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section E13: E2E (mocked) — Improvement metrics only when present

**Single goal:** With success mock that has improvement_metrics: null, assert "Improvement Metrics" section is not rendered. With success mock that has improvement_metrics set, assert "Improvement Metrics" and "Improved" or "Not Improved" are visible.

**Details:**
- Two tests or one parameterized: (1) response with improvement_metrics: null → no "Improvement Metrics" heading. (2) Response with improvement_metrics (e.g. improved: true) → "Improvement Metrics" and "Improved" visible. Ensures metrics block is conditional and correct.

**Tech stack and dependencies**
- Vitest, @testing-library/react. No new packages.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/frontend/src/App.test.tsx | Add tests: metrics absent vs present. |

**How to test:** `npm run test`; assert metrics section presence/absence per mock.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section E14: E2E (mocked) — Reset clears form and result

**Single goal:** After a successful run (mocked), click Reset; assert Job Status returns to "Idle", result section is gone, error message cleared, and form inputs are back to initial values (e.g. Run ID empty).

**Details:**
- Submit with mocked success; wait for Completed and result visible. Click "Reset" button. Assert status "Idle"; assert no "Completed" or result summary; assert Run ID (and Trace IDs) input values are empty or initial. Ensures full reset flow works.

**Tech stack and dependencies**
- Vitest, @testing-library/react. No new packages.

**Files and purpose**

| File | Purpose |
|------|--------|
| src/frontend/src/App.test.tsx | Add test: Reset after success clears state and form. |

**How to test:** `npm run test`; assert Idle and cleared form/result after Reset.

**Test results:** (Add when section is complete.)
- Command and outcome.

---

## Section E15: E2E — Live browser (optional): open app, submit tracer run, see result

**Single goal:** Using the Chrome DevTools workflow (no mocks), open the frontend in a real browser, submit a tracer run, and assert that either the harness change summary (or "no changes") or an error is visible. Validates the full stack with real backend when needed.

**Details:**
- Per AGENTS.md: `docker compose up -d backend frontend`; `docker compose stop chrome`; `./launch-devtools.sh http://localhost:5174`. In browser (or MCP/Playwright): navigate to http://localhost:5174, fill run_id (or trace_ids), click Run Tracer, wait for completion. Assert: Job Status "Completed" or "Failed"; if Completed, result summary or "No harness changes" visible; if Failed, error message visible. Document manual or automated in test results.

**Tech stack and dependencies**
- Docker Compose, Chrome (launch-devtools.sh), optional MCP browser or Playwright. No new packages for manual run.

**Files and purpose**

| File | Purpose |
|------|--------|
| (none for manual) | Verification only. Optional: E2E script or docs for browser steps. |

**How to test:** Follow AGENTS.md; run once with real backend; confirm result or error visible. Can be manual or automated (cursor-ide-browser, Playwright).

**Test results:** (Add when section is complete.)
- Command and outcome (manual or automated).

---
