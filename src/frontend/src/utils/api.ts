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
  change_id: string;
  title: string;
  category: "prompt" | "tool" | "config";
  priority: "low" | "medium" | "high" | "critical";
  confidence: number;
  prompt_edit?: {
    target: "system_prompt" | "planner_prompt" | "verification_prompt" | "other";
    action: "append" | "replace" | "remove" | "clarify";
    instruction: string;
    rationale: string;
    expected_outcome?: string | null;
  } | null;
  tool_change?: {
    tool_name: string;
    action: "add" | "update" | "remove";
    change_summary: string;
    rationale: string;
    interface: Record<string, unknown>;
    safety_notes?: string | null;
  } | null;
  config_change?: {
    key: string;
    action: "set" | "increase" | "decrease" | "remove";
    value?: unknown;
    scope: "tracer" | "sandbox" | "runtime" | "model" | "other";
    rationale: string;
  } | null;
};

export type HarnessChangeSet = {
  run_id?: string | null;
  trace_ids: string[];
  summary?: string | null;
  harness_changes: HarnessChange[];
  created_at: string;
};

export type ImprovementMetrics = {
  baseline: {
    command: string[];
    cwd?: string | null;
    timeout_seconds: number;
    exit_code: number;
    success: boolean;
    duration_ms: number;
    tests_passed?: number | null;
    tests_failed?: number | null;
    tests_skipped?: number | null;
    stdout_excerpt: string;
    stderr_excerpt: string;
  };
  post_change: {
    command: string[];
    cwd?: string | null;
    timeout_seconds: number;
    exit_code: number;
    success: boolean;
    duration_ms: number;
    tests_passed?: number | null;
    tests_failed?: number | null;
    tests_skipped?: number | null;
    stdout_excerpt: string;
    stderr_excerpt: string;
  };
  delta: {
    exit_code_delta: number;
    success_delta: number;
    tests_passed_delta?: number | null;
    tests_failed_delta?: number | null;
    tests_skipped_delta?: number | null;
    score_before?: number | null;
    score_after?: number | null;
    score_delta?: number | null;
  };
  improved: boolean;
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
