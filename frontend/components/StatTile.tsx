export default function StatTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: number | string;
  accent?: string;
}) {
  return (
    <div
      className="rounded-xl border px-5 py-4 flex-1 min-w-[140px]"
      style={{ borderColor: "var(--gridline)", background: "var(--surface-1)" }}
    >
      <div className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
        {label}
      </div>
      <div
        className="text-3xl font-semibold mt-1 tabular-nums"
        style={{ color: accent || "var(--text-primary)" }}
      >
        {value}
      </div>
    </div>
  );
}
