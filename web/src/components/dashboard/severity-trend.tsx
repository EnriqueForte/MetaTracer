const LEVELS = ["critical", "high", "medium", "low", "info", "unclassified"] as const;
type Level = (typeof LEVELS)[number];

export type TrendPoint = { date: string } & Record<Level, number>;

const LABEL: Record<Level, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  info: "Info",
  unclassified: "Unclassified",
};

const FILL: Record<Level, string> = {
  critical: "fill-mt-sev-critical",
  high: "fill-mt-sev-high",
  medium: "fill-mt-sev-medium",
  low: "fill-mt-sev-low",
  info: "fill-mt-sev-info",
  unclassified: "fill-mt-sev-unclassified",
};

const SWATCH: Record<Level, string> = {
  critical: "bg-mt-sev-critical",
  high: "bg-mt-sev-high",
  medium: "bg-mt-sev-medium",
  low: "bg-mt-sev-low",
  info: "bg-mt-sev-info",
  unclassified: "bg-mt-sev-unclassified",
};

const HEIGHT = 80;
const BAR = 8;
const GAP = 2;

export function parseTrend(value: unknown): TrendPoint[] {
  if (!Array.isArray(value)) return [];
  const points: TrendPoint[] = [];
  for (const row of value) {
    if (!row || typeof row !== "object") continue;
    const item = row as Record<string, unknown>;
    if (typeof item.date !== "string") continue;
    const point = { date: item.date } as TrendPoint;
    for (const level of LEVELS) point[level] = typeof item[level] === "number" ? (item[level] as number) : 0;
    points.push(point);
  }
  return points;
}

function total(point: TrendPoint): number {
  return LEVELS.reduce((sum, level) => sum + point[level], 0);
}

export function SeverityTrend({ points }: { points: TrendPoint[] }) {
  const peak = Math.max(1, ...points.map(total));
  const width = points.length * (BAR + GAP);
  const sum = points.reduce((count, point) => count + total(point), 0);
  const first = points[0]?.date ?? "";
  const last = points[points.length - 1]?.date ?? "";
  return (
    <section className="mt-card flex min-w-0 flex-col gap-3 p-4" aria-labelledby="severity-trend-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="severity-trend-title" className="mt-section-title">
          Findings per day
        </h2>
        <p className="mt-meta">
          {first} → {last} (UTC)
        </p>
      </div>
      {sum === 0 ? (
        <p className="text-sm text-mt-muted">No findings in the last {points.length} days.</p>
      ) : (
        <svg
          viewBox={`0 0 ${width} ${HEIGHT}`}
          preserveAspectRatio="none"
          className="h-24 w-full"
          role="img"
          aria-label={`${sum} findings over the last ${points.length} days`}
        >
          {points.map((point, index) => {
            let y = HEIGHT;
            return (
              <g key={point.date}>
                <title>{`${point.date}: ${total(point)} finding(s)`}</title>
                {LEVELS.map((level) => {
                  const height = (point[level] / peak) * HEIGHT;
                  if (height <= 0) return null;
                  y -= height;
                  return (
                    <rect
                      key={level}
                      x={index * (BAR + GAP)}
                      y={y}
                      width={BAR}
                      height={height}
                      className={FILL[level]}
                    />
                  );
                })}
              </g>
            );
          })}
        </svg>
      )}
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-mt-muted">
        {LEVELS.map((level) => (
          <li key={level} className="flex items-center gap-1.5">
            <span aria-hidden="true" className={`size-2.5 rounded-sm ${SWATCH[level]}`} />
            {LABEL[level]} {points.reduce((count, point) => count + point[level], 0)}
          </li>
        ))}
      </ul>
      <table className="sr-only">
        <caption>Findings per day by severity</caption>
        <thead>
          <tr>
            <th>Date</th>
            {LEVELS.map((level) => (
              <th key={level}>{LABEL[level]}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {points
            .filter((point) => total(point) > 0)
            .map((point) => (
              <tr key={point.date}>
                <td>{point.date}</td>
                {LEVELS.map((level) => (
                  <td key={level}>{point[level]}</td>
                ))}
              </tr>
            ))}
        </tbody>
      </table>
    </section>
  );
}
