"use client";

import { useEffect, useState } from "react";
import { api, ApiError, Report } from "@/lib/api";

export default function ReportsSection({ token, projectId }: { token: string; projectId: string }) {
  const [reports, setReports] = useState<Report[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);

  function refresh() {
    api
      .listReports(token, projectId)
      .then(setReports)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load reports."));
  }

  useEffect(refresh, [token, projectId]);

  async function handleGenerate() {
    setGenerateError(null);
    setGenerating(true);
    try {
      await api.createReport(token, projectId);
      refresh();
    } catch (err) {
      setGenerateError(err instanceof ApiError ? err.message : "Could not generate report.");
    } finally {
      setGenerating(false);
    }
  }

  async function togglePreview(reportId: string) {
    if (previewId === reportId) {
      setPreviewId(null);
      setPreviewHtml(null);
      return;
    }
    setPreviewId(reportId);
    setPreviewHtml(null);
    try {
      const html = await api.getReportContent(token, reportId);
      setPreviewHtml(html);
    } catch {
      setPreviewHtml("<p>Failed to load preview.</p>");
    }
  }

  async function handleDownload(report: Report) {
    const html = await api.getReportContent(token, report.id);
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${report.report_type}_${report.id.slice(0, 8)}.html`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="mt-8">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-medium" style={{ color: "var(--text-primary)" }}>
          Reports
        </h2>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="rounded-lg px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
          style={{ background: "var(--series-1)" }}
        >
          {generating ? "Generating…" : "Generate report"}
        </button>
      </div>

      {generateError && (
        <div className="text-sm mb-3" style={{ color: "var(--status-critical)" }}>
          {generateError}
        </div>
      )}
      {error && (
        <div className="text-sm" style={{ color: "var(--status-critical)" }}>
          {error}
        </div>
      )}
      {reports === null && !error && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          Loading…
        </div>
      )}
      {reports && reports.length === 0 && (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>
          No reports generated yet.
        </div>
      )}
      {reports && reports.length > 0 && (
        <div className="flex flex-col gap-3">
          {reports.map((r) => (
            <div
              key={r.id}
              className="rounded-xl border p-4"
              style={{ borderColor: "var(--gridline)", background: "var(--surface-1)" }}
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                    {r.report_type}
                  </div>
                  <div className="text-xs mt-0.5 font-mono" style={{ color: "var(--text-muted)" }}>
                    {new Date(r.created_at).toLocaleString()} · sha256:{r.content_hash.slice(0, 12)}…
                  </div>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => togglePreview(r.id)}
                    className="text-xs font-medium px-2 py-1 rounded-md"
                    style={{ color: "var(--series-1)" }}
                  >
                    {previewId === r.id ? "Hide" : "Preview"}
                  </button>
                  <button
                    onClick={() => handleDownload(r)}
                    className="text-xs font-medium px-2 py-1 rounded-md"
                    style={{ color: "var(--series-1)" }}
                  >
                    Download
                  </button>
                </div>
              </div>
              {previewId === r.id && (
                <div className="mt-3 rounded-lg overflow-hidden border" style={{ borderColor: "var(--gridline)" }}>
                  {previewHtml === null ? (
                    <div className="text-xs p-3" style={{ color: "var(--text-muted)" }}>
                      Loading preview…
                    </div>
                  ) : (
                    <iframe title={`report-${r.id}`} srcDoc={previewHtml} className="w-full" style={{ height: 400 }} />
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
