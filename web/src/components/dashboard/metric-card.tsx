import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

function MetricCard({
  label,
  value,
  detail,
  href,
}: {
  label: string;
  value: string;
  detail: ReactNode;
  href?: string;
}) {
  const className = cn(
    "mt-card relative flex min-w-0 flex-col gap-3 overflow-hidden p-4 pl-5",
    href ? "mt-card-interactive" : null,
  );
  const body = (
    <>
      <span aria-hidden="true" className="absolute inset-y-0 left-0 w-0.5 bg-mt-border-strong" />
      <p className="mt-kicker">{label}</p>
      <p className="mt-metric-value">{value}</p>
      <p className="mt-meta">{detail}</p>
    </>
  );
  if (href) {
    return (
      <Link href={href} className={className}>
        {body}
      </Link>
    );
  }
  return <article className={className}>{body}</article>;
}

export { MetricCard };
