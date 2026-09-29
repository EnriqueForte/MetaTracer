import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

function Card({
  className,
  interactive = false,
  ...props
}: HTMLAttributes<HTMLDivElement> & { interactive?: boolean }) {
  return <div className={cn("mt-card", interactive && "mt-card-interactive", className)} {...props} />;
}

export { Card };
