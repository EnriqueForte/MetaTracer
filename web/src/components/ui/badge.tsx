import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center whitespace-nowrap rounded-sm border border-transparent px-1.5 py-0.5 text-[11px] font-semibold leading-tight tracking-wide",
  {
    variants: {
      variant: {
        critical: "bg-mt-sev-critical-bg text-mt-sev-critical",
        high: "bg-mt-sev-high-bg text-mt-sev-high",
        medium: "bg-mt-sev-medium-bg text-mt-sev-medium",
        low: "bg-mt-sev-low-bg text-mt-sev-low",
        info: "bg-mt-sev-info-bg text-mt-sev-info",
        unclassified: "border-mt-border-strong bg-transparent text-mt-sev-unclassified",
        pending: "border-mt-border-strong bg-transparent text-mt-muted",
        running: "border-mt-accent bg-transparent text-mt-accent-hover",
        completed: "bg-mt-success-bg text-mt-success",
        failed: "bg-mt-danger-bg text-mt-danger",
        aborted: "bg-mt-warning-bg text-mt-warning",
        confidence: "border-mt-border-strong bg-transparent text-mt-fg",
      },
    },
    defaultVariants: {
      variant: "info",
    },
  },
);

function Badge({
  className,
  variant,
  ...props
}: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
