import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";

function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mt-card px-5 py-8">
      <p className="mt-section-title">{title}</p>
      {children ? <div className="mt-2 max-w-prose text-sm text-mt-muted">{children}</div> : null}
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-mt-danger-border bg-mt-danger-bg px-4 py-3 text-sm text-mt-fg"
    >
      <p>{message}</p>
      {onRetry ? (
        <Button variant="secondary" onClick={onRetry}>
          Reintentar
        </Button>
      ) : null}
    </div>
  );
}

function LoadingState({ label = "Cargando" }: { label?: string }) {
  return (
    <div role="status" aria-busy="true" className="flex flex-col gap-3">
      <span className="sr-only">{label}</span>
      <div className="mt-skeleton h-8 w-48" />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="mt-skeleton h-24" />
        <div className="mt-skeleton h-24" />
        <div className="mt-skeleton h-24" />
        <div className="mt-skeleton h-24" />
      </div>
    </div>
  );
}

export { EmptyState, ErrorState, LoadingState };
