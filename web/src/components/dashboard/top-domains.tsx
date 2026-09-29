function share(count: number, total: number): number {
  if (count <= 0 || total <= 0) return 0;
  return Math.min(100, (count / total) * 100);
}

function TopDomains({ rows }: { rows: { domain: string; count: number }[] }) {
  const max = Math.max(1, ...rows.map((entry) => entry.count));
  return (
    <section className="mt-card flex min-w-0 flex-col gap-4 p-4" aria-labelledby="top-domains-title">
      <h2 id="top-domains-title" className="mt-section-title">
        Top domains
      </h2>
      {rows.length === 0 ? (
        <p className="mt-meta">No scopes or assets scanned yet.</p>
      ) : (
        <ol className="flex flex-col gap-3">
          {rows.map((entry, index) => (
            <li key={entry.domain} className="grid grid-cols-[1.5rem_minmax(0,1fr)_2.5rem] items-center gap-2">
              <span className="text-xs tabular-nums text-mt-faint">{index + 1}</span>
              <div className="min-w-0">
                <p className="mt-tech truncate" title={entry.domain}>
                  {entry.domain}
                </p>
                <div className="mt-chart-track mt-1" aria-hidden="true">
                  <span className="mt-chart-fill bg-mt-chart-2" style={{ width: `${share(entry.count, max)}%` }} />
                </div>
              </div>
              <span className="text-right text-xs tabular-nums text-mt-fg">{entry.count}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export { TopDomains };
