"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError, Job } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  queued: "var(--status-neutral)",
  running: "var(--series-1)",
  completed: "var(--status-good)",
  failed: "var(--status-critical)",
};

const TERMINAL = new Set(["completed", "failed"]);

export default function JobsSection({ token, projectId }: { token: string; projectId: string }) {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function refresh() {
    api
      .listJobs(token, projectId)
      .then(setJobs)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load jobs."));
  }

  useEffect(() => {
    refresh();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, projectId]);

  function pollUntilTerminal(jobId: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    let attempts = 0;
    pollRef.current = setInterval(() => {
      attempts += 1;
      api
        .getJob(token, jobId)
        .then((job) => {
          setJobs((prev) => (prev ? prev.map((j) => (j.id === job.id ? job : j)) : prev));
          if (TERMINAL.has(job.status) || attempts > 20) {
            if (pollRef.current) clearInterval(pollRef.current);
          }
        })
        .catch(() => {
          if (pollRef.current) clearInterval(pollRef.current);
        });
    }, 1500);
  }

  async function handleSubmit() {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const job = await api.createJob(token, projectId);
      setJobs((prev) => (prev ? [job, ...prev] : [job]));
      pollUntilTerminal(job.id);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Could not submit job.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mt-8">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-medium" style={{ color: "var(--text-primary)" }}>
          Pipeline jobs
        </h2>
        <button
          onClick={handleSubmit}
          disabled={submitting}
          className="rounded-lg px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
          style={{ background: "var(--series-1)" }}
        >
          {submitting ? "Submitting…" : "Submit job"}
        </button>
      </div>

      {submitError && (
        <div
          className="text-sm rounded-lg px-3 py-2 mb-3"
          style={{ background: "color-mix(in oklab, var(--status-critical) 12%, transparent)", color: "var(--status-critical)" }}
        >
          {submitError}
        </div>
      )}

      {error && (
        <div className="text-sm" style={{ color: "var(--status-critical)" }}>
          {error}
        </div>
      )}
      {jobs === null && !error && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          Loading…
        </div>
      )}
      {jobs && jobs.length === 0 && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          No pipeline jobs yet.
        </div>
      )}
      {jobs && jobs.length > 0 && (
        <div
          className="rounded-xl border divide-y"
          style={{ borderColor: "var(--gridline)", background: "var(--surface-1)" }}
        >
          {jobs.map((job) => (
            <div key={job.id} className="px-4 py-3 flex items-center gap-3" style={{ borderColor: "var(--gridline)" }}>
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ background: STATUS_COLOR[job.status] || "var(--status-neutral)" }}
              />
              <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                {job.pipeline_name}
              </span>
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                {new Date(job.created_at).toLocaleString()}
              </span>
              <span
                className="text-xs font-mono ml-auto px-2 py-0.5 rounded-full"
                style={{ background: "var(--page-plane)", color: STATUS_COLOR[job.status] || "var(--text-secondary)" }}
              >
                {job.status}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
