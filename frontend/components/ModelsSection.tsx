"use client";

import { useEffect, useState, FormEvent } from "react";
import { api, ApiError, Job, MLModel } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  draft: "var(--status-warning)",
  approved: "var(--status-good)",
  deprecated: "var(--status-neutral)",
};

export default function ModelsSection({
  token,
  projectId,
  userRole,
}: {
  token: string;
  projectId: string;
  userRole: string;
}) {
  const [models, setModels] = useState<MLModel[] | null>(null);
  const [completedJobs, setCompletedJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [jobId, setJobId] = useState("");
  const [name, setName] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [approveErrors, setApproveErrors] = useState<Record<string, string>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  function refresh() {
    api
      .listModels(token, projectId)
      .then(setModels)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load models."));
    api
      .listJobs(token, projectId)
      .then((jobs) => setCompletedJobs(jobs.filter((j) => j.status === "completed")))
      .catch(() => {});
  }

  useEffect(refresh, [token, projectId]);

  async function handleRegister(e: FormEvent) {
    e.preventDefault();
    if (!jobId) {
      setFormError("Choose a completed job.");
      return;
    }
    setFormError(null);
    setSubmitting(true);
    try {
      await api.registerModel(token, projectId, { job_id: jobId, name: name || undefined });
      setName("");
      setJobId("");
      setShowForm(false);
      refresh();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not register model.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleApprove(modelId: string) {
    setApproveErrors((prev) => ({ ...prev, [modelId]: "" }));
    try {
      await api.approveModel(token, modelId);
      refresh();
    } catch (err) {
      setApproveErrors((prev) => ({
        ...prev,
        [modelId]: err instanceof ApiError ? err.message : "Could not approve model.",
      }));
    }
  }

  return (
    <div className="mt-8">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-medium" style={{ color: "var(--text-primary)" }}>
          Models
        </h2>
        <button
          onClick={() => {
            const next = !showForm;
            setShowForm(next);
            if (next) refresh();
          }}
          className="rounded-lg px-3 py-1.5 text-sm font-medium text-white"
          style={{ background: "var(--series-1)" }}
        >
          {showForm ? "Cancel" : "Register model"}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={handleRegister}
          className="rounded-xl border p-5 mb-6 flex flex-wrap items-end gap-3"
          style={{ borderColor: "var(--gridline)", background: "var(--surface-1)" }}
        >
          <div>
            <label htmlFor="jobSelect" className="text-sm font-medium block mb-1" style={{ color: "var(--text-secondary)" }}>
              Completed job
            </label>
            <select
              id="jobSelect"
              value={jobId}
              onChange={(e) => setJobId(e.target.value)}
              className="rounded-lg border px-3 py-2 text-sm outline-none"
              style={{ borderColor: "var(--gridline)", background: "var(--page-plane)", color: "var(--text-primary)" }}
            >
              <option value="">Select a completed job…</option>
              {completedJobs.map((j) => (
                <option key={j.id} value={j.id}>
                  {j.pipeline_name} — {new Date(j.created_at).toLocaleString()}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="modelName" className="text-sm font-medium block mb-1" style={{ color: "var(--text-secondary)" }}>
              Model name (optional)
            </label>
            <input
              id="modelName"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded-lg border px-3 py-2 text-sm outline-none"
              style={{ borderColor: "var(--gridline)", background: "var(--page-plane)", color: "var(--text-primary)" }}
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            style={{ background: "var(--series-1)" }}
          >
            {submitting ? "Registering…" : "Register"}
          </button>
          {completedJobs.length === 0 && (
            <div className="text-xs w-full" style={{ color: "var(--text-muted)" }}>
              No completed jobs yet for this project.
            </div>
          )}
          {formError && (
            <div className="text-sm w-full" style={{ color: "var(--status-critical)" }}>
              {formError}
            </div>
          )}
        </form>
      )}

      {error && (
        <div className="text-sm" style={{ color: "var(--status-critical)" }}>
          {error}
        </div>
      )}
      {models === null && !error && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          Loading…
        </div>
      )}
      {models && models.length === 0 && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          No models registered yet.
        </div>
      )}
      {models && models.length > 0 && (
        <div className="flex flex-col gap-3">
          {models.map((m) => {
            const isExpanded = !!expanded[m.id];
            return (
              <div
                key={m.id}
                className="rounded-xl border p-4"
                style={{ borderColor: "var(--gridline)", background: "var(--surface-1)" }}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                        {m.name}
                      </span>
                      <span
                        className="text-xs font-mono px-2 py-0.5 rounded-full"
                        style={{ background: "var(--page-plane)", color: STATUS_COLOR[m.approval_status] }}
                      >
                        {m.approval_status}
                      </span>
                    </div>
                    <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                      {m.algorithm} · target: {m.target_variable}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => setExpanded((prev) => ({ ...prev, [m.id]: !prev[m.id] }))}
                      className="text-xs font-medium px-2 py-1 rounded-md"
                      style={{ color: "var(--series-1)" }}
                    >
                      {isExpanded ? "Hide details" : "Details"}
                    </button>
                    {m.approval_status === "draft" &&
                      (userRole === "administrator" ? (
                        <button
                          onClick={() => handleApprove(m.id)}
                          className="text-xs font-medium px-2 py-1 rounded-md text-white"
                          style={{ background: "var(--status-good)" }}
                        >
                          Approve
                        </button>
                      ) : (
                        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                          Requires Administrator
                        </span>
                      ))}
                  </div>
                </div>
                {approveErrors[m.id] && (
                  <div className="text-xs mt-2" style={{ color: "var(--status-critical)" }}>
                    {approveErrors[m.id]}
                  </div>
                )}
                {isExpanded && (
                  <div className="mt-3 pl-3 border-l flex flex-col gap-2" style={{ borderColor: "var(--gridline)" }}>
                    {m.metrics && (
                      <div>
                        <div className="text-xs font-medium mb-1" style={{ color: "var(--text-secondary)" }}>
                          Metrics
                        </div>
                        <pre
                          className="text-xs whitespace-pre-wrap rounded-md p-2"
                          style={{ background: "var(--page-plane)", color: "var(--text-secondary)" }}
                        >
                          {m.metrics}
                        </pre>
                      </div>
                    )}
                    <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
                      <strong style={{ color: "var(--text-primary)" }}>Intended use:</strong> {m.intended_use}
                    </div>
                    <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
                      <strong style={{ color: "var(--text-primary)" }}>Prohibited use:</strong> {m.prohibited_use}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
