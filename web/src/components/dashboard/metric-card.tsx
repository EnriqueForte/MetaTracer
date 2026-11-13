import type { ReactNode } from "react";

function MetricCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: ReactNode;
}) {
  return (
    <article className="mt-card relative flex min-w-0 flex-col gap-3 overflow-hidden p-4 pl-5">
      <span aria-hidden="true" className="absolute inset-y-0 left-0 w-0.5 bg-mt-border-strong" />
      <p className="mt-kicker">{label}</p>
      <p className="mt-metric-value">{value}</p>
      <p className="mt-meta">{detail}</p>
    </article>
  );
}

export { MetricCard };
