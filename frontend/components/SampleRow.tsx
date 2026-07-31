"use client";

import { useRef, useState, FormEvent } from "react";
import { api, ApiError, Sample, Upload } from "@/lib/api";

const OMICS_TYPES = [
  "",
  "genomic",
  "metagenomic",
  "transcriptomic",
  "proteomic",
  "metabolomic",
  "environmental metadata",
];

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function SampleRow({ token, sample }: { token: string; sample: Sample }) {
  const [expanded, setExpanded] = useState(false);
  const [uploads, setUploads] = useState<Upload[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [omicsType, setOmicsType] = useState("");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function refresh() {
    api
      .listUploads(token, sample.id)
      .then(setUploads)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load uploads."));
  }

  function toggle() {
    const next = !expanded;
    setExpanded(next);
    if (next && uploads === null) refresh();
  }

  async function handleUpload(e: FormEvent) {
    e.preventDefault();
    const file = fileInputRef.current?.files?.[0];
    if (!file) {
      setUploadError("Choose a file first.");
      return;
    }
    setUploadError(null);
    setUploading(true);
    try {
      await api.createUpload(token, sample.id, file, omicsType || undefined);
      setOmicsType("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      refresh();
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <li className="text-sm" style={{ color: "var(--text-secondary)" }}>
      <button onClick={toggle} className="flex items-center gap-2 w-full text-left">
        <span
          className="text-xs font-mono px-1.5 py-0.5 rounded"
          style={{ background: "var(--page-plane)", color: "var(--text-secondary)" }}
        >
          rep {sample.replicate}
        </span>
        {sample.lab_identifier && <span>{sample.lab_identifier}</span>}
        {sample.sample_type && <span style={{ color: "var(--text-muted)" }}>{sample.sample_type}</span>}
        <span className="text-xs ml-auto" style={{ color: "var(--text-muted)" }}>
          {sample.analysis_status}
        </span>
      </button>

      {expanded && (
        <div className="mt-2 pl-3 border-l" style={{ borderColor: "var(--gridline)" }}>
          {error && (
            <div className="text-xs" style={{ color: "var(--status-critical)" }}>
              {error}
            </div>
          )}
          {uploads === null && !error && (
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              Loading…
            </div>
          )}
          {uploads && uploads.length === 0 && (
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              No files uploaded yet.
            </div>
          )}
          {uploads && uploads.length > 0 && (
            <ul className="flex flex-col gap-1 mb-2">
              {uploads.map((u) => (
                <li key={u.id} className="text-xs flex items-center gap-2" style={{ color: "var(--text-secondary)" }}>
                  <span style={{ color: "var(--text-primary)" }}>{u.original_filename}</span>
                  <span style={{ color: "var(--text-muted)" }}>{formatBytes(u.size_bytes)}</span>
                  {u.omics_type && <span style={{ color: "var(--text-muted)" }}>· {u.omics_type}</span>}
                  <span
                    className="ml-auto"
                    style={{
                      color:
                        u.validation_status === "valid" ? "var(--status-good)" : "var(--status-warning)",
                    }}
                  >
                    {u.validation_status}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <form onSubmit={handleUpload} className="flex flex-wrap items-end gap-2">
            <input
              ref={fileInputRef}
              type="file"
              aria-label="File"
              className="text-xs"
              style={{ color: "var(--text-secondary)" }}
            />
            <select
              aria-label="Omics type"
              value={omicsType}
              onChange={(e) => setOmicsType(e.target.value)}
              className="rounded-md border px-2 py-1 text-xs outline-none"
              style={{ borderColor: "var(--gridline)", background: "var(--page-plane)", color: "var(--text-primary)" }}
            >
              {OMICS_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t || "(unspecified type)"}
                </option>
              ))}
            </select>
            <button
              type="submit"
              disabled={uploading}
              className="rounded-md px-2 py-1 text-xs font-medium text-white disabled:opacity-60"
              style={{ background: "var(--series-1)" }}
            >
              {uploading ? "Uploading…" : "Upload"}
            </button>
          </form>
          {uploadError && (
            <div className="text-xs mt-1" style={{ color: "var(--status-critical)" }}>
              {uploadError}
            </div>
          )}
        </div>
      )}
    </li>
  );
}
