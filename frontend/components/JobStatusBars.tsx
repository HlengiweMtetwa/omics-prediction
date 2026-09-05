interface Row {
  label: string;
  value: number;
  color: string;
}

export default function JobStatusBars({
  queued,
  running,
  completed,
  failed,
}: {
  queued: number;
  running: number;
  completed: number;
  failed: number;
}) {
  const rows: Row[] = [
    { label: "Queued", value: queued, color: "var(--status-neutral)" },
    { label: "Running", value: running, color: "var(--series-1)" },
    { label: "Completed", value: completed, color: "var(--status-good)" },
    { label: "Failed", value: failed, color: "var(--status-critical)" },
  ];
  const max = Math.max(1, ...rows.map((r) => r.value));

  return (
    <div className="flex flex-col gap-3">
      {rows.map((row) => (
        <div key={row.label} className="flex items-center gap-3">
          <div className="w-24 text-sm shrink-0" style={{ color: "var(--text-secondary)" }}>
            {row.label}
          </div>
          <div
            className="flex-1 h-2 rounded-full overflow-hidden"
            style={{ background: "var(--gridline)" }}
          >
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${(row.value / max) * 100}%`,
                background: row.color,
              }}
            />
          </div>
          <div
            className="w-8 text-sm text-right tabular-nums shrink-0"
            style={{ color: "var(--text-primary)" }}
          >
            {row.value}
          </div>
        </div>
      ))}
    </div>
  );
}
