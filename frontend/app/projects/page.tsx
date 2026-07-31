"use client";

import { useEffect, useState, FormEvent } from "react";
import { useRequireAuth } from "@/lib/auth-context";
import { api, ApiError, Project } from "@/lib/api";
import AppShell from "@/components/AppShell";

export default function ProjectsPage() {
  const { token, loading: authLoading } = useRequireAuth();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [diseaseFocus, setDiseaseFocus] = useState("");
  const [amrFocus, setAmrFocus] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function refresh() {
    if (!token) return;
    api
      .listProjects(token)
      .then(setProjects)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load projects."));
  }

  useEffect(refresh, [token]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setFormError(null);
    setSubmitting(true);
    try {
      await api.createProject(token, {
        title,
        description: description || undefined,
        disease_focus: diseaseFocus || undefined,
        amr_focus: amrFocus,
      });
      setTitle("");
      setDescription("");
      setDiseaseFocus("");
      setAmrFocus(false);
      setShowForm(false);
      refresh();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not create project.");
    } finally {
      setSubmitting(false);
    }
  }

  if (authLoading || !token) return null;

  return (
    <AppShell>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
            Projects
          </h1>
          <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
            Surveillance projects you own.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="rounded-lg px-4 py-2 text-sm font-medium text-white"
          style={{ background: "var(--series-1)" }}
        >
          {showForm ? "Cancel" : "New project"}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={handleCreate}
          className="rounded-xl border p-5 mb-6 flex flex-col gap-4"
          style={{ borderColor: "var(--gridline)", background: "var(--surface-1)" }}
        >
          <div>
            <label htmlFor="title" className="text-sm font-medium block mb-1" style={{ color: "var(--text-secondary)" }}>
              Title
            </label>
            <input
              id="title"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
              style={{ borderColor: "var(--gridline)", background: "var(--page-plane)", color: "var(--text-primary)" }}
            />
          </div>
          <div>
            <label htmlFor="description" className="text-sm font-medium block mb-1" style={{ color: "var(--text-secondary)" }}>
              Description
            </label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
              style={{ borderColor: "var(--gridline)", background: "var(--page-plane)", color: "var(--text-primary)" }}
            />
          </div>
          <div className="flex gap-4">
            <div className="flex-1">
              <label htmlFor="diseaseFocus" className="text-sm font-medium block mb-1" style={{ color: "var(--text-secondary)" }}>
                Disease / AMR focus
              </label>
              <input
                id="diseaseFocus"
                value={diseaseFocus}
                onChange={(e) => setDiseaseFocus(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                style={{ borderColor: "var(--gridline)", background: "var(--page-plane)", color: "var(--text-primary)" }}
              />
            </div>
            <label htmlFor="amrFocus" className="flex items-center gap-2 text-sm mt-6" style={{ color: "var(--text-secondary)" }}>
              <input id="amrFocus" type="checkbox" checked={amrFocus} onChange={(e) => setAmrFocus(e.target.checked)} />
              AMR focus
            </label>
          </div>

          {formError && (
            <div
              className="text-sm rounded-lg px-3 py-2"
              style={{ background: "color-mix(in oklab, var(--status-critical) 12%, transparent)", color: "var(--status-critical)" }}
            >
              {formError}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="self-start rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            style={{ background: "var(--series-1)" }}
          >
            {submitting ? "Creating…" : "Create project"}
          </button>
        </form>
      )}

      {error && (
        <div
          className="text-sm rounded-lg px-3 py-2 mb-4"
          style={{ background: "color-mix(in oklab, var(--status-critical) 12%, transparent)", color: "var(--status-critical)" }}
        >
          {error}
        </div>
      )}

      {projects === null && !error && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          Loading…
        </div>
      )}

      {projects && projects.length === 0 && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          No projects yet. Create one above.
        </div>
      )}

      {projects && projects.length > 0 && (
        <div className="flex flex-col gap-3">
          {projects.map((p) => (
            <div
              key={p.id}
              className="rounded-xl border p-4"
              style={{ borderColor: "var(--gridline)", background: "var(--surface-1)" }}
            >
              <div className="flex items-center justify-between">
                <h3 className="font-medium" style={{ color: "var(--text-primary)" }}>
                  {p.title}
                </h3>
                <span
                  className="text-xs font-mono px-2 py-0.5 rounded-full"
                  style={{ background: "var(--page-plane)", color: "var(--text-secondary)" }}
                >
                  {p.status}
                </span>
              </div>
              {p.description && (
                <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
                  {p.description}
                </p>
              )}
              <div className="text-xs mt-2 flex gap-3" style={{ color: "var(--text-muted)" }}>
                {p.disease_focus && <span>Disease focus: {p.disease_focus}</span>}
                {p.amr_focus && <span>AMR focus</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </AppShell>
  );
}
