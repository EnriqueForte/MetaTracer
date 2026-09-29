import type { ReactNode } from "react";

export function AuthPanel({
  title,
  lede,
  children,
  note,
}: {
  title: string;
  lede: string;
  children: ReactNode;
  note?: ReactNode;
}) {
  return (
    <main id="main-content" className="mt-auth">
      <div className="mt-auth-panel">
        <div>
          <p className="text-xs text-mt-muted">MetaTracer</p>
          <h1 className="mt-title">{title}</h1>
          <p className="text-sm text-mt-muted">{lede}</p>
        </div>
        {children}
      </div>
      {note ? <div className="mt-auth-note">{note}</div> : null}
    </main>
  );
}
