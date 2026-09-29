import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
  accentClass,
}: {
  label: string;
  value: string;
  detail: ReactNode;
  icon: LucideIcon;
  accentClass: string;
}) {
  return (
    <article className="mt-card mt-card-interactive relative flex min-w-0 flex-col gap-3 overflow-hidden p-4">
      <span aria-hidden="true" className={cn("absolute inset-x-0 top-0 h-0.5", accentClass)} />
      <div className="flex items-start justify-between gap-3">
        <h2 className="mt-kicker">{label}</h2>
        <span
          className="flex size-8 shrink-0 items-center justify-center rounded-md border border-mt-border bg-mt-elevated text-mt-muted"
          aria-hidden="true"
        >
          <Icon className="size-4" />
        </span>
      </div>
      <p className="mt-metric-value">{value}</p>
      <p className="mt-meta">{detail}</p>
    </article>
  );
}

export { MetricCard };
