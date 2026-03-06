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
          harness_changes: [],
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
  });

  it("renders backend error message when run fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Provide at least one of run_id or trace_ids." }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.change(screen.getByLabelText("Run ID"), { target: { value: "run-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Run Tracer" }));

    expect(await screen.findByText("Failed")).toBeTruthy();
    expect(screen.getByText("Provide at least one of run_id or trace_ids.")).toBeTruthy();
  });
});
