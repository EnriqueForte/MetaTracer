import { typeFill, typeLabel } from "@/components/dashboard/labels";

function share(count: number, total: number): number {
  if (count <= 0 || total <= 0) return 0;
  return Math.min(100, (count / total) * 100);
}

function FindingsTypeChart({ rows }: { rows: [string, number][] }) {
  const max = Math.max(1, ...rows.map(([, count]) => count));
  return (
    <section className="mt-card flex min-w-0 flex-col gap-4 p-4" aria-labelledby="findings-type-title">
      <h2 id="findings-type-title" className="mt-section-title">
        Hallazgos por tipo
      </h2>
      {rows.length === 0 ? (
        <p className="mt-meta">Aún no hay hallazgos.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {rows.map(([type, count]) => {
            const label = typeLabel(type);
            return (
              <div
                key={type}
                data-chart-row="true"
                className="grid grid-cols-[minmax(0,8.5rem)_minmax(0,1fr)_2.5rem] items-center gap-2"
                title={`${label}: ${count}`}
              >
                <span className="truncate text-xs text-mt-muted">{label}</span>
                <div className="mt-chart-track" role="img" aria-label={`${label}: ${count}`}>
                  <span data-bar="true" className={`mt-chart-fill ${typeFill(type)}`} style={{ width: `${share(count, max)}%` }} />
                </div>
                <span className="text-right text-xs tabular-nums text-mt-fg">{count}</span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

export { FindingsTypeChart };
