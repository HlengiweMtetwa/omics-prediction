"use client";

import { useEffect, useState } from "react";
import { useRequireAuth } from "@/lib/auth-context";
import { api, ApiError, DashboardSummary } from "@/lib/api";
import AppShell from "@/components/AppShell";
import StatTile from "@/components/StatTile";
import JobStatusBars from "@/components/JobStatusBars";

export default function DashboardPage() {
  const { token, loading: authLoading } = useRequireAuth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api
      .dashboard(token)
      .then(setSummary)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load dashboard."));
  }, [token]);

  if (authLoading || !token) return null;

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
        Overview
      </h1>
      <p className="text-sm mt-1 mb-6" style={{ color: "var(--text-secondary)" }}>
        Your projects, sites, samples, and pipeline activity.
      </p>

      {error && (
        <div
          className="text-sm rounded-lg px-3 py-2 mb-6"
          style={{ background: "color-mix(in oklab, var(--status-critical) 12%, transparent)", color: "var(--status-critical)" }}
        >
          {error}
        </div>
      )}

      {!summary && !error && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          Loading…
        </div>
      )}

      {summary && (
        <div className="flex flex-col gap-8">
          <div className="flex flex-wrap gap-4">
            <StatTile label="Active projects" value={summary.active_projects} />
            <StatTile label="Sites" value={summary.sites} />
            <StatTile label="Samples" value={summary.samples} />
          </div>

          <div
            className="rounded-xl border p-5"
            style={{ borderColor: "var(--gridline)", background: "var(--surface-1)" }}
          >
            <h2 className="text-sm font-semibold mb-4" style={{ color: "var(--text-primary)" }}>
              Pipeline jobs
            </h2>
            <JobStatusBars
              queued={summary.jobs_queued}
              running={summary.jobs_running}
              completed={summary.jobs_completed}
              failed={summary.jobs_failed}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div
              className="rounded-xl border p-5"
              style={{ borderColor: "var(--gridline)", background: "var(--surface-1)" }}
            >
              <h2 className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
                Approved models ({summary.approved_models.length})
              </h2>
              {summary.approved_models.length === 0 ? (
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                  None yet.
                </p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {summary.approved_models.map((m) => (
                    <li key={m.id} className="text-sm flex items-center gap-2">
                      <span
                        className="inline-block w-2 h-2 rounded-full shrink-0"
                        style={{ background: "var(--status-good)" }}
                      />
                      <span className="font-medium" style={{ color: "var(--text-primary)" }}>
                        {m.name}
                      </span>
                      <span style={{ color: "var(--text-muted)" }}>— {m.algorithm}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div
              className="rounded-xl border p-5"
              style={{ borderColor: "var(--gridline)", background: "var(--surface-1)" }}
            >
              <h2 className="text-sm font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
                Recent activity
              </h2>
              {summary.recent_activity.length === 0 ? (
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                  No activity yet.
                </p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {summary.recent_activity.map((e, i) => (
                    <li key={i} className="text-xs" style={{ color: "var(--text-secondary)" }}>
                      <span className="tabular-nums" style={{ color: "var(--text-muted)" }}>
                        {new Date(e.created_at).toLocaleString()}
                      </span>{" "}
                      — {e.action}
                      {e.details ? ` (${e.details})` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
