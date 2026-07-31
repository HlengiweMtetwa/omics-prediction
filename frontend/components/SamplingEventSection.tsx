"use client";

import { useState, FormEvent } from "react";
import { api, ApiError, Sample, SamplingEvent } from "@/lib/api";
import SampleRow from "./SampleRow";

export default function SamplingEventSection({
  token,
  event,
}: {
  token: string;
  event: SamplingEvent;
}) {
  const [expanded, setExpanded] = useState(false);
  const [samples, setSamples] = useState<Sample[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [sampleType, setSampleType] = useState("");
  const [replicate, setReplicate] = useState(1);
  const [labIdentifier, setLabIdentifier] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function refresh() {
    api
      .listSamples(token, event.id)
      .then(setSamples)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load samples."));
  }

  function toggle() {
    const next = !expanded;
    setExpanded(next);
    if (next && samples === null) refresh();
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setSubmitting(true);
    try {
      await api.createSample(token, event.id, {
        sample_type: sampleType || undefined,
        replicate,
        lab_identifier: labIdentifier || undefined,
      });
      setSampleType("");
      setReplicate((replicate || 1) + 1);
      setLabIdentifier("");
      setShowForm(false);
      refresh();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not create sample.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-lg border p-3" style={{ borderColor: "var(--gridline)" }}>
      <div className="flex items-center justify-between">
        <button
          onClick={toggle}
          className="text-sm font-medium text-left"
          style={{ color: "var(--text-primary)" }}
        >
          {new Date(event.collected_at).toLocaleString()}
          {event.sample_matrix && (
            <span className="ml-2 font-normal" style={{ color: "var(--text-muted)" }}>
              {event.sample_matrix}
            </span>
          )}
        </button>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="text-xs font-medium px-2 py-1 rounded-md"
          style={{ color: "var(--series-1)" }}
        >
          {showForm ? "Cancel" : "+ Sample"}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="mt-3 flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor={`sampleType-${event.id}`} className="text-xs block mb-1" style={{ color: "var(--text-secondary)" }}>
              Sample type
            </label>
            <input
              id={`sampleType-${event.id}`}
              value={sampleType}
              onChange={(e) => setSampleType(e.target.value)}
              className="rounded-md border px-2 py-1 text-sm outline-none"
              style={{ borderColor: "var(--gridline)", background: "var(--page-plane)", color: "var(--text-primary)" }}
            />
          </div>
          <div>
            <label htmlFor={`replicate-${event.id}`} className="text-xs block mb-1" style={{ color: "var(--text-secondary)" }}>
              Replicate
            </label>
            <input
              id={`replicate-${event.id}`}
              type="number"
              min={1}
              required
              value={replicate}
              onChange={(e) => setReplicate(Number(e.target.value))}
              className="w-20 rounded-md border px-2 py-1 text-sm outline-none"
              style={{ borderColor: "var(--gridline)", background: "var(--page-plane)", color: "var(--text-primary)" }}
            />
          </div>
          <div>
            <label htmlFor={`labId-${event.id}`} className="text-xs block mb-1" style={{ color: "var(--text-secondary)" }}>
              Lab identifier
            </label>
            <input
              id={`labId-${event.id}`}
              value={labIdentifier}
              onChange={(e) => setLabIdentifier(e.target.value)}
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
            {submitting ? "Adding…" : "Add sample"}
          </button>
          {formError && (
            <div className="text-xs w-full" style={{ color: "var(--status-critical)" }}>
              {formError}
            </div>
          )}
        </form>
      )}

      {expanded && (
        <div className="mt-3 pl-3 border-l" style={{ borderColor: "var(--gridline)" }}>
          {error && (
            <div className="text-xs" style={{ color: "var(--status-critical)" }}>
              {error}
            </div>
          )}
          {samples === null && !error && (
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              Loading…
            </div>
          )}
          {samples && samples.length === 0 && (
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              No samples yet.
            </div>
          )}
          {samples && samples.length > 0 && (
            <ul className="flex flex-col gap-2">
              {samples.map((s) => (
                <SampleRow key={s.id} token={token} sample={s} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
