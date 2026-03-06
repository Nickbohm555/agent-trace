const API_BASE_URL = import.meta.env.VITE_BACKEND_URL ?? "http://localhost:8001";

export type TracerRunRequest = {
  run_id?: string;
  trace_ids?: string[];
  target_repo_url?: string;
  run_name?: string;
  from_timestamp?: string;
  to_timestamp?: string;
  limit?: number;
  environment?: string;
  max_runtime_seconds?: number;
  max_steps?: number;
};

export type HarnessChange = {
  title: string;
  summary: string;
  file_path?: string | null;
  patch?: string | null;
  rationale?: string | null;
};

export type HarnessChangeSet = {
  run_id: string;
  trace_ids: string[];
  summary: string;
  harness_changes: HarnessChange[];
};

export type ImprovementMetrics = {
  baseline_exit_code: number;
  candidate_exit_code: number;
  baseline_duration_seconds: number;
  candidate_duration_seconds: number;
  command: string[];
  command_cwd: string | null;
  tests_passed_before: boolean;
  tests_passed_after: boolean;
  pass_delta: number;
  duration_delta_seconds: number;
  baseline_stdout_tail: string[];
  baseline_stderr_tail: string[];
  candidate_stdout_tail: string[];
  candidate_stderr_tail: string[];
};

export type TracerRunResponse = {
  run_id: string;
  target_repo_url: string;
  trace_ids: string[];
  fetched_trace_count: number;
  persisted_trace_count: number;
  loaded_trace_count: number;
  harness_change_set: HarnessChangeSet;
  improvement_metrics?: ImprovementMetrics | null;
};

async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    if (typeof payload.detail === "string" && payload.detail.trim() !== "") {
      return payload.detail;
    }
  } catch {
    // Ignore json parse failure and return fallback below.
  }
  return `Tracer run failed with status ${response.status}.`;
}

export async function runTracer(request: TracerRunRequest): Promise<TracerRunResponse> {
  const response = await fetch(`${API_BASE_URL}/api/tracer/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const errorMessage = await parseErrorMessage(response);
    throw new Error(errorMessage);
  }

  return (await response.json()) as TracerRunResponse;
}
