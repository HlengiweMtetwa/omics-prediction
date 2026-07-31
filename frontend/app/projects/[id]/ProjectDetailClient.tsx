"use client";

import { useEffect, useState, FormEvent } from "react";
import Link from "next/link";
import { useRequireAuth } from "@/lib/auth-context";
import { api, ApiError, Project, Site } from "@/lib/api";
import AppShell from "@/components/AppShell";
import SiteSection from "@/components/SiteSection";

export default function ProjectDetailClient({ projectId }: { projectId: string }) {
  const { token, loading: authLoading } = useRequireAuth();
  const [project, setProject] = useState<Project | null>(null);
  const [sites, setSites] = useState<Site[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [country, setCountry] = useState("");
  const [region, setRegion] = useState("");
  const [siteType, setSiteType] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function refreshSites() {
    if (!token) return;
    api
      .listSites(token, projectId)
      .then(setSites)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load sites."));
  }

  useEffect(() => {
    if (!token) return;
    api
      .getProject(token, projectId)
      .then(setProject)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load project."));
    refreshSites();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, projectId]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setFormError(null);
    setSubmitting(true);
    try {
      await api.createSite(token, projectId, {
        name,
        country: country || undefined,
        region: region || undefined,
        site_type: siteType || undefined,
      });
      setName("");
      setCountry("");
      setRegion("");
      setSiteType("");
      setShowForm(false);
      refreshSites();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not create site.");
    } finally {
      setSubmitting(false);
    }
  }

  if (authLoading || !token) return null;

  return (
    <AppShell>
      <Link href="/projects" className="text-sm font-medium" style={{ color: "var(--series-1)" }}>
        ← Projects
      </Link>

      {error && (
        <div
          className="text-sm rounded-lg px-3 py-2 mt-4"
          style={{ background: "color-mix(in oklab, var(--status-critical) 12%, transparent)", color: "var(--status-critical)" }}
        >
          {error}
        </div>
      )}

      {project && (
        <div className="mt-3 mb-6">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
              {project.title}
            </h1>
            <span
              className="text-xs font-mono px-2 py-0.5 rounded-full"
              style={{ background: "var(--surface-1)", color: "var(--text-secondary)" }}
            >
              {project.status}
            </span>
          </div>
          {project.description && (
            <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
              {project.description}
            </p>
          )}
          <div className="text-xs mt-2 flex gap-3" style={{ color: "var(--text-muted)" }}>
            {project.disease_focus && <span>Disease focus: {project.disease_focus}</span>}
            {project.amr_focus && <span>AMR focus</span>}
          </div>
        </div>
      )}

      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-medium" style={{ color: "var(--text-primary)" }}>
          Sites
        </h2>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="rounded-lg px-3 py-1.5 text-sm font-medium text-white"
          style={{ background: "var(--series-1)" }}
        >
          {showForm ? "Cancel" : "New site"}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={handleCreate}
          className="rounded-xl border p-5 mb-6 flex flex-wrap items-end gap-3"
          style={{ borderColor: "var(--gridline)", background: "var(--surface-1)" }}
        >
          <div>
            <label htmlFor="siteName" className="text-sm font-medium block mb-1" style={{ color: "var(--text-secondary)" }}>
              Name
            </label>
            <input
              id="siteName"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded-lg border px-3 py-2 text-sm outline-none"
              style={{ borderColor: "var(--gridline)", background: "var(--page-plane)", color: "var(--text-primary)" }}
            />
          </div>
          <div>
            <label htmlFor="siteType" className="text-sm font-medium block mb-1" style={{ color: "var(--text-secondary)" }}>
              Site type
            </label>
            <input
              id="siteType"
              value={siteType}
              onChange={(e) => setSiteType(e.target.value)}
              className="rounded-lg border px-3 py-2 text-sm outline-none"
              style={{ borderColor: "var(--gridline)", background: "var(--page-plane)", color: "var(--text-primary)" }}
            />
          </div>
          <div>
            <label htmlFor="siteRegion" className="text-sm font-medium block mb-1" style={{ color: "var(--text-secondary)" }}>
              Region
            </label>
            <input
              id="siteRegion"
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="rounded-lg border px-3 py-2 text-sm outline-none"
              style={{ borderColor: "var(--gridline)", background: "var(--page-plane)", color: "var(--text-primary)" }}
            />
          </div>
          <div>
            <label htmlFor="siteCountry" className="text-sm font-medium block mb-1" style={{ color: "var(--text-secondary)" }}>
              Country
            </label>
            <input
              id="siteCountry"
              value={country}
              onChange={(e) => setCountry(e.target.value)}
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
            {submitting ? "Creating…" : "Create site"}
          </button>
          {formError && (
            <div className="text-sm w-full" style={{ color: "var(--status-critical)" }}>
              {formError}
            </div>
          )}
        </form>
      )}

      {sites === null && !error && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          Loading…
        </div>
      )}
      {sites && sites.length === 0 && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          No sites yet. Create one above.
        </div>
      )}
      {sites && sites.length > 0 && (
        <div className="flex flex-col gap-3">
          {sites.map((site) => (
            <SiteSection key={site.id} token={token} site={site} />
          ))}
        </div>
      )}
    </AppShell>
  );
}
