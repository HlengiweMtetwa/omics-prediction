"use client";

import { useState, FormEvent } from "react";
import { api, ApiError, SamplingEvent, Site } from "@/lib/api";
import SamplingEventSection from "./SamplingEventSection";

function nowForInput() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

export default function SiteSection({ token, site }: { token: string; site: Site }) {
  const [expanded, setExpanded] = useState(false);
  const [events, setEvents] = useState<SamplingEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [collectedAt, setCollectedAt] = useState(nowForInput());
  const [sampleMatrix, setSampleMatrix] = useState("");
  const [collector, setCollector] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function refresh() {
    api
      .listSamplingEvents(token, site.id)
      .then(setEvents)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load sampling events."));
  }

  function toggle() {
    const next = !expanded;
    setExpanded(next);
    if (next && events === null) refresh();
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setSubmitting(true);
    try {
      await api.createSamplingEvent(token, site.id, {
        collected_at: new Date(collectedAt).toISOString(),
        sample_matrix: sampleMatrix || undefined,
        collector: collector || undefined,
      });
      setSampleMatrix("");
      setCollector("");
      setShowForm(false);
      refresh();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not create sampling event.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="rounded-xl border p-4"
      style={{ borderColor: "var(--gridline)", background: "var(--surface-1)" }}
    >
      <div className="flex items-center justify-between">
        <button onClick={toggle} className="text-left">
          <div className="font-medium" style={{ color: "var(--text-primary)" }}>
            {site.name}
          </div>
          <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
            {[site.site_type, site.region, site.country].filter(Boolean).join(" · ") || "No location details"}
          </div>
        </button>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="text-xs font-medium px-2 py-1 rounded-md shrink-0"
          style={{ color: "var(--series-1)" }}
        >
          {showForm ? "Cancel" : "+ Sampling event"}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="mt-3 flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor={`collectedAt-${site.id}`} className="text-xs block mb-1" style={{ color: "var(--text-secondary)" }}>
              Collected at
            </label>
            <input
              id={`collectedAt-${site.id}`}
              type="datetime-local"
              required
              value={collectedAt}
              onChange={(e) => setCollectedAt(e.target.value)}
              className="rounded-md border px-2 py-1 text-sm outline-none"
              style={{ borderColor: "var(--gridline)", background: "var(--page-plane)", color: "var(--text-primary)" }}
            />
          </div>
          <div>
            <label htmlFor={`matrix-${site.id}`} className="text-xs block mb-1" style={{ color: "var(--text-secondary)" }}>
              Sample matrix
            </label>
            <input
              id={`matrix-${site.id}`}
              value={sampleMatrix}
              onChange={(e) => setSampleMatrix(e.target.value)}
              className="rounded-md border px-2 py-1 text-sm outline-none"
              style={{ borderColor: "var(--gridline)", background: "var(--page-plane)", color: "var(--text-primary)" }}
            />
          </div>
          <div>
            <label htmlFor={`collector-${site.id}`} className="text-xs block mb-1" style={{ color: "var(--text-secondary)" }}>
              Collector
            </label>
            <input
              id={`collector-${site.id}`}
              value={collector}
              onChange={(e) => setCollector(e.target.value)}
              className="rounded-md border px-2 py-1 text-sm outline-none"
              style={{ borderColor: "var(--gridline)", background: "var(--page-plane)", color: "var(--text-primary)" }}
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
            style={{ background: "var(--series-1)" }}
          >
            {submitting ? "Adding…" : "Add event"}
          </button>
          {formError && (
            <div className="text-xs w-full" style={{ color: "var(--status-critical)" }}>
              {formError}
            </div>
          )}
        </form>
      )}

      {expanded && (
        <div className="mt-3 flex flex-col gap-2">
          {error && (
            <div className="text-xs" style={{ color: "var(--status-critical)" }}>
              {error}
            </div>
          )}
          {events === null && !error && (
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              Loading…
            </div>
          )}
          {events && events.length === 0 && (
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              No sampling events yet.
            </div>
          )}
          {events?.map((event) => (
            <SamplingEventSection key={event.id} token={token} event={event} />
          ))}
        </div>
      )}
    </div>
  );
}
