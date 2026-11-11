import { SEVERITY_LABEL } from "@/lib/ui-copy";
import { cn } from "@/lib/utils";

const SEVERITIES = ["critical", "high", "medium", "low", "info", "unclassified"] as const;

const SEVERITY_FILL: Record<(typeof SEVERITIES)[number], string> = {
  critical: "bg-mt-sev-critical text-mt-sev-critical",
  high: "bg-mt-sev-high text-mt-sev-high",
  medium: "bg-mt-sev-medium text-mt-sev-medium",
  low: "bg-mt-sev-low text-mt-sev-low",
  info: "bg-mt-sev-info text-mt-sev-info",
  unclassified: "bg-mt-sev-unclassified text-mt-sev-unclassified",
};

function SeverityOverview({
  total,
  breakdown,
}: {
  total: number;
  breakdown: Record<string, number>;
}) {
  const parts = SEVERITIES.map((severity) => ({
    key: severity,
    label: SEVERITY_LABEL[severity],
    value: breakdown[severity] ?? 0,
    tone: SEVERITY_FILL[severity],
  }));
  const sum = parts.reduce((count, part) => count + part.value, 0);
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const segments: { key: string; label: string; value: number; tone: string; start: number; length: number }[] = [];
  let cursor = 0;
  for (const part of parts) {
    if (part.value <= 0 || sum <= 0) continue;
    const length = (part.value / sum) * circumference;
    segments.push({ ...part, start: cursor, length });
    cursor += length;
  }

  return (
    <section className="mt-card flex min-w-0 flex-col gap-4 p-4" aria-labelledby="security-posture-title">
      <h2 id="security-posture-title" className="mt-section-title">
        Postura de seguridad
      </h2>
      <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-center">
        <svg viewBox="0 0 120 120" className="h-40 w-40 shrink-0" role="img" aria-label={`${total} hallazgos`}>
          <circle cx="60" cy="60" r={radius} fill="none" stroke="var(--mt-elevated)" strokeWidth="12" />
          {segments.map((segment) => (
            <circle
              key={segment.key}
              cx="60"
              cy="60"
              r={radius}
              fill="none"
              stroke="currentColor"
              strokeWidth="12"
              strokeDasharray={`${segment.length} ${circumference - segment.length}`}
              strokeDashoffset={-segment.start}
              className={segment.tone}
              transform="rotate(-90 60 60)"
            >
              <title>{`${segment.label} ${segment.value}`}</title>
            </circle>
          ))}
          <text x="60" y="58" textAnchor="middle" fill="var(--mt-fg)" fontSize="18" fontWeight="600">
            {total}
          </text>
          <text x="60" y="74" textAnchor="middle" fill="var(--mt-muted)" fontSize="8" letterSpacing="0.08em">
            HALLAZGOS
          </text>
        </svg>
        <ul className="grid w-full min-w-0 gap-1.5">
          {parts.map((part) => (
            <li key={part.key} className="flex items-center justify-between gap-3 text-sm">
              <span className="flex min-w-0 items-center gap-2">
                <span data-swatch="true" aria-hidden="true" className={cn("size-2.5 shrink-0 rounded-sm", part.tone)} />
                <span className="text-mt-muted">{part.label}</span>
              </span>
              <span className="tabular-nums text-mt-fg">{part.value}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export { SeverityOverview };
