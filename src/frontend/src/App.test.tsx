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

  it("submits run payload and renders completion summary", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        run_id: "run-123",
        target_repo_url: "https://example.com/repo.git",
        trace_ids: ["trace-1", "trace-2"],
        fetched_trace_count: 2,
        persisted_trace_count: 2,
        loaded_trace_count: 2,
        harness_change_set: {
          run_id: "run-123",
          trace_ids: ["trace-1", "trace-2"],
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
        improvement_metrics: {
          baseline: {
            command: ["uv", "run", "pytest", "tests/api", "-m", "smoke"],
            cwd: null,
            timeout_seconds: 900,
            exit_code: 1,
            success: false,
            duration_ms: 15000,
            tests_passed: 18,
            tests_failed: 2,
            tests_skipped: 0,
            stdout_excerpt: "2 failed, 18 passed",
            stderr_excerpt: "",
          },
          post_change: {
            command: ["uv", "run", "pytest", "tests/api", "-m", "smoke"],
            cwd: null,
            timeout_seconds: 900,
            exit_code: 0,
            success: true,
            duration_ms: 14200,
            tests_passed: 20,
            tests_failed: 0,
            tests_skipped: 0,
            stdout_excerpt: "20 passed",
            stderr_excerpt: "",
          },
          delta: {
            exit_code_delta: -1,
            success_delta: 1,
            tests_passed_delta: 2,
            tests_failed_delta: -2,
            tests_skipped_delta: 0,
            score_before: 18,
            score_after: 20,
            score_delta: 2,
          },
          improved: true,
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.change(screen.getByLabelText("Run ID"), { target: { value: "run-123" } });
    fireEvent.change(screen.getByLabelText("Trace IDs (comma-separated)"), {
      target: { value: "trace-1, trace-2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run Tracer" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0]?.[0]).toContain("/api/tracer/run");

    const requestBody = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}")) as {
      run_id: string;
      trace_ids: string[];
    };
    expect(requestBody.run_id).toBe("run-123");
    expect(requestBody.trace_ids).toEqual(["trace-1", "trace-2"]);
    expect(await screen.findByText("Completed")).toBeTruthy();
    expect(screen.getByText("Synthesized one harness change.")).toBeTruthy();
    expect(screen.getByText("Clarify verification prompt")).toBeTruthy();
    expect(screen.getByText("Improvement Metrics")).toBeTruthy();
    expect(screen.getByText("Improved")).toBeTruthy();
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
