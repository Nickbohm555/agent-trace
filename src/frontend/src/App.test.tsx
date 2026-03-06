// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("App tracer run UI", () => {
  it("disables submit and shows hint until run id or trace ids are provided", () => {
    render(<App />);

    const submitButton = screen.getByRole("button", { name: "Run Tracer" });
    const runIdInput = screen.getByLabelText("Run ID");
    const traceIdsInput = screen.getByLabelText("Trace IDs (comma-separated)");

    expect(submitButton).toHaveProperty("disabled", true);
    expect(screen.getByText("Provide `Run ID` or at least one `Trace ID`.")).toBeTruthy();

    fireEvent.change(runIdInput, { target: { value: "run-123" } });
    expect(submitButton).toHaveProperty("disabled", false);

    fireEvent.change(runIdInput, { target: { value: "" } });
    fireEvent.change(traceIdsInput, { target: { value: "trace-a, trace-b" } });
    expect(submitButton).toHaveProperty("disabled", false);
  });

  it("submits run_id only payload and renders completion summary with harness changes", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        run_id: "run-123",
        target_repo_url: "https://example.com/repo.git",
        trace_ids: [],
        fetched_trace_count: 0,
        persisted_trace_count: 0,
        loaded_trace_count: 0,
        harness_change_set: {
          run_id: "run-123",
          trace_ids: [],
          summary: "Synthesized one harness change.",
          created_at: "2026-03-06T00:00:00Z",
          harness_changes: [
            {
              change_id: "chg-1",
              title: "Clarify verification prompt",
              category: "prompt",
              priority: "high",
              confidence: 0.84,
              prompt_edit: {
                target: "verification_prompt",
                action: "append",
                instruction: "Always run smoke tests before returning done.",
                rationale: "Missed regressions were observed in failing traces.",
                expected_outcome: "Fewer false positive completions.",
              },
            },
          ],
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.change(screen.getByLabelText("Run ID"), { target: { value: "run-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Run Tracer" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0]?.[0]).toContain("/api/tracer/run");

    const requestBody = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}")) as {
      run_id?: string;
      trace_ids?: string[];
    };
    expect(requestBody.run_id).toBe("run-123");
    expect(requestBody.trace_ids).toBeUndefined();
    expect(await screen.findByText("Completed")).toBeTruthy();
    expect(screen.getByText("Synthesized one harness change.")).toBeTruthy();
    expect(screen.getByText("Clarify verification prompt")).toBeTruthy();
  });

  it("submits trace_ids only payload and renders completed result", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        run_id: "generated-run-from-traces",
        target_repo_url: "https://example.com/repo.git",
        trace_ids: ["trace-a", "trace-b"],
        fetched_trace_count: 2,
        persisted_trace_count: 2,
        loaded_trace_count: 2,
        harness_change_set: {
          run_id: "generated-run-from-traces",
          trace_ids: ["trace-a", "trace-b"],
          summary: "Synthesized one harness change from explicit traces.",
          created_at: "2026-03-06T00:00:00Z",
          harness_changes: [
            {
              change_id: "chg-2",
              title: "Add deterministic retry guidance",
              category: "prompt",
              priority: "medium",
              confidence: 0.71,
              prompt_edit: {
                target: "planner_prompt",
                action: "append",
                instruction: "Retry once with a narrower scope before concluding failure.",
                rationale: "Trace-only runs showed flaky first-pass edits.",
                expected_outcome: "Higher completion reliability for trace-driven runs.",
              },
            },
          ],
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.change(screen.getByLabelText("Trace IDs (comma-separated)"), {
      target: { value: "trace-a, trace-b" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run Tracer" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0]?.[0]).toContain("/api/tracer/run");

    const requestBody = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}")) as {
      run_id?: string;
      trace_ids?: string[];
    };
    expect(requestBody.run_id).toBeUndefined();
    expect(requestBody.trace_ids).toEqual(["trace-a", "trace-b"]);
    expect(await screen.findByText("Completed")).toBeTruthy();
    expect(screen.getByText("Synthesized one harness change from explicit traces.")).toBeTruthy();
    expect(screen.getByText("Add deterministic retry guidance")).toBeTruthy();
  });

  it("renders empty harness changes state and hides improvement metrics when none are returned", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        run_id: "run-empty-1",
        target_repo_url: "https://example.com/repo.git",
        trace_ids: [],
        fetched_trace_count: 0,
        persisted_trace_count: 0,
        loaded_trace_count: 0,
        harness_change_set: {
          run_id: "run-empty-1",
          trace_ids: [],
          summary: "No harness changes were synthesized by the tracer graph.",
          created_at: "2026-03-06T00:00:00Z",
          harness_changes: [],
        },
        improvement_metrics: null,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.change(screen.getByLabelText("Run ID"), { target: { value: "run-empty-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Run Tracer" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Completed")).toBeTruthy();
    expect(screen.getByText("No harness changes were synthesized by the tracer graph.")).toBeTruthy();
    expect(screen.getByText("No harness changes were returned by this run.")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Improvement Metrics" })).toBeNull();
  });

  it("shows running state while tracer request is in flight and resets controls on completion", async () => {
    const fetchMock = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(() => {
            resolve({
              ok: true,
              json: async () => ({
                run_id: "run-delayed-1",
                target_repo_url: "https://example.com/repo.git",
                trace_ids: [],
                fetched_trace_count: 0,
                persisted_trace_count: 0,
                loaded_trace_count: 0,
                harness_change_set: {
                  run_id: "run-delayed-1",
                  trace_ids: [],
                  summary: "Delayed run completed successfully.",
                  created_at: "2026-03-06T00:00:00Z",
                  harness_changes: [],
                },
                improvement_metrics: null,
              }),
            });
          }, 50);
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.change(screen.getByLabelText("Run ID"), { target: { value: "run-delayed-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Run Tracer" }));

    expect(screen.getByRole("button", { name: "Running..." })).toBeTruthy();
    expect(screen.getByText("Running")).toBeTruthy();

    expect(await screen.findByText("Completed")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Run Tracer" })).toBeTruthy();
    expect(screen.getByText("Delayed run completed successfully.")).toBeTruthy();
  });

  it("renders backend error message when run fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({
        detail: [
          {
            type: "value_error",
            loc: ["body"],
            msg: "Value error, Provide at least one of run_id or trace_ids.",
          },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.change(screen.getByLabelText("Run ID"), { target: { value: "run-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Run Tracer" }));

    expect(await screen.findByText("Failed")).toBeTruthy();
    expect(screen.getByText("Value error, Provide at least one of run_id or trace_ids.")).toBeTruthy();
  });
});
