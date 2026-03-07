import { FormEvent, useMemo, useState } from "react";
import { HarnessChange, ImprovementMetrics, TracerRunResponse, runTracer } from "./utils/api";
import "./styles.css";

type RunState = "idle" | "running" | "completed" | "failed";

type FormState = {
  runId: string;
  traceIds: string;
  targetRepoUrl: string;
  runName: string;
  environment: string;
  fromTimestamp: string;
  toTimestamp: string;
  limit: string;
  maxRuntimeSeconds: string;
  maxSteps: string;
};

const initialFormState: FormState = {
  runId: "",
  traceIds: "",
  targetRepoUrl: "",
  runName: "",
  environment: "",
  fromTimestamp: "",
  toTimestamp: "",
  limit: "50",
  maxRuntimeSeconds: "",
  maxSteps: "",
};

function splitTraceIds(raw: string): string[] {
  return raw
    .split(",")
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
}

function formatMillisAsSeconds(durationMs: number): string {
  return `${(durationMs / 1000).toFixed(2)}s`;
}

function formatOptionalNumber(value?: number | null): string {
  return value === null || value === undefined ? "n/a" : String(value);
}

function renderHarnessChangeDetails(change: HarnessChange) {
  if (change.category === "prompt" && change.prompt_edit) {
    return (
      <dl className="change-details">
        <dt>Target</dt>
        <dd>{change.prompt_edit.target}</dd>
        <dt>Action</dt>
        <dd>{change.prompt_edit.action}</dd>
        <dt>Instruction</dt>
        <dd>{change.prompt_edit.instruction}</dd>
        <dt>Rationale</dt>
        <dd>{change.prompt_edit.rationale}</dd>
        {change.prompt_edit.expected_outcome ? (
          <>
            <dt>Expected Outcome</dt>
            <dd>{change.prompt_edit.expected_outcome}</dd>
          </>
        ) : null}
      </dl>
    );
  }

  if (change.category === "tool" && change.tool_change) {
    return (
      <dl className="change-details">
        <dt>Tool</dt>
        <dd>{change.tool_change.tool_name}</dd>
        <dt>Action</dt>
        <dd>{change.tool_change.action}</dd>
        <dt>Summary</dt>
        <dd>{change.tool_change.change_summary}</dd>
        <dt>Rationale</dt>
        <dd>{change.tool_change.rationale}</dd>
        <dt>Interface</dt>
        <dd>
          <pre>{JSON.stringify(change.tool_change.interface, null, 2)}</pre>
        </dd>
        {change.tool_change.safety_notes ? (
          <>
            <dt>Safety Notes</dt>
            <dd>{change.tool_change.safety_notes}</dd>
          </>
        ) : null}
      </dl>
    );
  }

  if (change.category === "config" && change.config_change) {
    return (
      <dl className="change-details">
        <dt>Key</dt>
        <dd>{change.config_change.key}</dd>
        <dt>Action</dt>
        <dd>{change.config_change.action}</dd>
        <dt>Scope</dt>
        <dd>{change.config_change.scope}</dd>
        <dt>Value</dt>
        <dd>{JSON.stringify(change.config_change.value)}</dd>
        <dt>Rationale</dt>
        <dd>{change.config_change.rationale}</dd>
      </dl>
    );
  }

  return <p className="hint">No category payload was included for this change.</p>;
}

function renderMetrics(metrics: ImprovementMetrics) {
  return (
    <div className="metrics">
      <h3>Improvement Metrics</h3>
      <p className={`status ${metrics.improved ? "status-completed" : "status-idle"}`}>
        {metrics.improved ? "Improved" : "Not Improved"}
      </p>

      <div className="metrics-grid">
        <article className="metrics-card">
          <h4>Baseline</h4>
          <dl>
            <dt>Exit Code</dt>
            <dd>{metrics.baseline.exit_code}</dd>
            <dt>Success</dt>
            <dd>{String(metrics.baseline.success)}</dd>
            <dt>Duration</dt>
            <dd>{formatMillisAsSeconds(metrics.baseline.duration_ms)}</dd>
            <dt>Passed</dt>
            <dd>{formatOptionalNumber(metrics.baseline.tests_passed)}</dd>
            <dt>Failed</dt>
            <dd>{formatOptionalNumber(metrics.baseline.tests_failed)}</dd>
            <dt>Skipped</dt>
            <dd>{formatOptionalNumber(metrics.baseline.tests_skipped)}</dd>
            <dt>Command</dt>
            <dd>{metrics.baseline.command.join(" ")}</dd>
          </dl>
        </article>

        <article className="metrics-card">
          <h4>Post Change</h4>
          <dl>
            <dt>Exit Code</dt>
            <dd>{metrics.post_change.exit_code}</dd>
            <dt>Success</dt>
            <dd>{String(metrics.post_change.success)}</dd>
            <dt>Duration</dt>
            <dd>{formatMillisAsSeconds(metrics.post_change.duration_ms)}</dd>
            <dt>Passed</dt>
            <dd>{formatOptionalNumber(metrics.post_change.tests_passed)}</dd>
            <dt>Failed</dt>
            <dd>{formatOptionalNumber(metrics.post_change.tests_failed)}</dd>
            <dt>Skipped</dt>
            <dd>{formatOptionalNumber(metrics.post_change.tests_skipped)}</dd>
            <dt>Command</dt>
            <dd>{metrics.post_change.command.join(" ")}</dd>
          </dl>
        </article>

        <article className="metrics-card">
          <h4>Delta</h4>
          <dl>
            <dt>Exit Code Delta</dt>
            <dd>{metrics.delta.exit_code_delta}</dd>
            <dt>Success Delta</dt>
            <dd>{metrics.delta.success_delta}</dd>
            <dt>Passed Delta</dt>
            <dd>{formatOptionalNumber(metrics.delta.tests_passed_delta)}</dd>
            <dt>Failed Delta</dt>
            <dd>{formatOptionalNumber(metrics.delta.tests_failed_delta)}</dd>
            <dt>Skipped Delta</dt>
            <dd>{formatOptionalNumber(metrics.delta.tests_skipped_delta)}</dd>
            <dt>Score Before</dt>
            <dd>{formatOptionalNumber(metrics.delta.score_before)}</dd>
            <dt>Score After</dt>
            <dd>{formatOptionalNumber(metrics.delta.score_after)}</dd>
            <dt>Score Delta</dt>
            <dd>{formatOptionalNumber(metrics.delta.score_delta)}</dd>
          </dl>
        </article>
      </div>
    </div>
  );
}

export default function App() {
  const [formState, setFormState] = useState<FormState>(initialFormState);
  const [runState, setRunState] = useState<RunState>("idle");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [result, setResult] = useState<TracerRunResponse | null>(null);

  const traceIdCount = useMemo(() => splitTraceIds(formState.traceIds).length, [formState.traceIds]);
  const canSubmit = formState.runId.trim().length > 0 || traceIdCount > 0;

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit || runState === "running") {
      return;
    }

    setRunState("running");
    setErrorMessage("");
    setResult(null);

    const traceIds = splitTraceIds(formState.traceIds);
    const payload = {
      run_id: formState.runId.trim() || undefined,
      trace_ids: traceIds.length > 0 ? traceIds : undefined,
      target_repo_url: formState.targetRepoUrl.trim() || undefined,
      run_name: formState.runName.trim() || undefined,
      environment: formState.environment.trim() || undefined,
      from_timestamp: formState.fromTimestamp || undefined,
      to_timestamp: formState.toTimestamp || undefined,
      limit: formState.limit.trim() ? Number(formState.limit) : undefined,
      max_runtime_seconds: formState.maxRuntimeSeconds.trim()
        ? Number(formState.maxRuntimeSeconds)
        : undefined,
      max_steps: formState.maxSteps.trim() ? Number(formState.maxSteps) : undefined,
    };

    console.info("Submitting tracer run request", {
      runId: payload.run_id,
      traceIdCount: payload.trace_ids?.length ?? 0,
      targetRepoUrl: payload.target_repo_url ?? "default",
    });

    try {
      const runResult = await runTracer(payload);
      console.info("Tracer run completed", {
        runId: runResult.run_id,
        harnessChangeCount: runResult.harness_change_set.harness_changes.length,
        metricsAvailable: runResult.improvement_metrics !== null && runResult.improvement_metrics !== undefined,
      });
      setResult(runResult);
      setRunState("completed");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to start tracer run.";
      console.error("Tracer run failed", { error: message });
      setErrorMessage(message);
      setRunState("failed");
    }
  };

  return (
    <main className="app-shell">
      <section className="panel">
        <h1>Tracer Run Console</h1>
        <p>Submit a Langfuse run or explicit trace IDs to trigger a tracer analysis run.</p>

        <form className="tracer-form" onSubmit={onSubmit}>
          <label>
            Run ID
            <input
              name="run-id"
              value={formState.runId}
              onChange={(event) => setFormState((prev) => ({ ...prev, runId: event.target.value }))}
              placeholder="run-123"
            />
          </label>

          <label>
            Trace IDs (comma-separated)
            <input
              name="trace-ids"
              value={formState.traceIds}
              onChange={(event) => setFormState((prev) => ({ ...prev, traceIds: event.target.value }))}
              placeholder="trace-a, trace-b"
            />
          </label>

          <label>
            Target Repo URL
            <input
              name="target-repo-url"
              value={formState.targetRepoUrl}
              onChange={(event) => setFormState((prev) => ({ ...prev, targetRepoUrl: event.target.value }))}
              placeholder="https://github.com/org/repo"
            />
          </label>

          <label>
            Run Name
            <input
              name="run-name"
              value={formState.runName}
              onChange={(event) => setFormState((prev) => ({ ...prev, runName: event.target.value }))}
              placeholder="experiment-a"
            />
          </label>

          <label>
            Environment
            <input
              name="environment"
              value={formState.environment}
              onChange={(event) => setFormState((prev) => ({ ...prev, environment: event.target.value }))}
              placeholder="production"
            />
          </label>

          <div className="row">
            <label>
              From Timestamp
              <input
                name="from-timestamp"
                type="datetime-local"
                value={formState.fromTimestamp}
                onChange={(event) =>
                  setFormState((prev) => ({ ...prev, fromTimestamp: event.target.value }))
                }
              />
            </label>

            <label>
              To Timestamp
              <input
                name="to-timestamp"
                type="datetime-local"
                value={formState.toTimestamp}
                onChange={(event) => setFormState((prev) => ({ ...prev, toTimestamp: event.target.value }))}
              />
            </label>
          </div>

          <div className="row">
            <label>
              Limit
              <input
                name="limit"
                type="number"
                min={1}
                max={500}
                value={formState.limit}
                onChange={(event) => setFormState((prev) => ({ ...prev, limit: event.target.value }))}
              />
            </label>

            <label>
              Max Runtime Seconds
              <input
                name="max-runtime-seconds"
                type="number"
                min={1}
                max={7200}
                value={formState.maxRuntimeSeconds}
                onChange={(event) =>
                  setFormState((prev) => ({ ...prev, maxRuntimeSeconds: event.target.value }))
                }
              />
            </label>

            <label>
              Max Steps
              <input
                name="max-steps"
                type="number"
                min={1}
                max={200}
                value={formState.maxSteps}
                onChange={(event) => setFormState((prev) => ({ ...prev, maxSteps: event.target.value }))}
              />
            </label>
          </div>

          <div className="actions">
            <button type="submit" disabled={!canSubmit || runState === "running"}>
              {runState === "running" ? "Running..." : "Run Tracer"}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                console.info("Resetting tracer run form and UI state");
                setFormState(initialFormState);
                setErrorMessage("");
                setResult(null);
                setRunState("idle");
              }}
            >
              Reset
            </button>
          </div>

          {!canSubmit ? <p className="hint">Provide `Run ID` or at least one `Trace ID`.</p> : null}
        </form>
      </section>

      <section className="panel">
        <h2>Job Status</h2>
        <p className={`status status-${runState}`}>
          {runState === "idle" && "Idle"}
          {runState === "running" && "Running"}
          {runState === "completed" && "Completed"}
          {runState === "failed" && "Failed"}
        </p>

        {errorMessage ? <p className="error">{errorMessage}</p> : null}

        {result ? (
          <div className="result">
            <h3>Run Summary</h3>
            <dl>
              <dt>Run ID</dt>
              <dd>{result.run_id}</dd>
              <dt>Target Repo</dt>
              <dd>{result.target_repo_url}</dd>
              <dt>Trace IDs</dt>
              <dd>{result.trace_ids.join(", ") || "None returned"}</dd>
              <dt>Fetched/Persisted/Loaded</dt>
              <dd>
                {result.fetched_trace_count}/{result.persisted_trace_count}/{result.loaded_trace_count}
              </dd>
              <dt>Harness Changes</dt>
              <dd>{result.harness_change_set.harness_changes.length}</dd>
            </dl>
            <p>{result.harness_change_set.summary ?? "No summary returned."}</p>

            <h3>Harness Changes</h3>
            {result.harness_change_set.harness_changes.length === 0 ? (
              <p className="hint">No harness changes were returned by this run.</p>
            ) : (
              <ul className="change-list">
                {result.harness_change_set.harness_changes.map((change) => (
                  <li key={change.change_id} className="change-item">
                    <h4>{change.title}</h4>
                    <p className="change-meta">
                      {change.change_id} | {change.category} | {change.priority} | confidence{" "}
                      {change.confidence.toFixed(2)}
                    </p>
                    {renderHarnessChangeDetails(change)}
                  </li>
                ))}
              </ul>
            )}

            {result.improvement_metrics ? renderMetrics(result.improvement_metrics) : null}
          </div>
        ) : null}
      </section>
    </main>
  );
}
