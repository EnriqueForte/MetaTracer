"use client";

import { useEffect, useState } from "react";

export function formatElapsed(startedAt: string | null | undefined, now: number): string {
  if (!startedAt) return "—";
  const iso = /[zZ]|[+-]\d\d:\d\d$/.test(startedAt) ? startedAt : `${startedAt}Z`;
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return "—";
  const total = Math.max(0, Math.floor((now - at) / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

/** What the operator can see without a live stage event. */
export function activityCopy(assets: number, findings: number, stageLabel: string | null): {
  title: string;
  detail: string;
} {
  if (stageLabel) {
    return {
      title: stageLabel,
      detail: "This is the step the scan just reported.",
    };
  }
  if (findings > 0) {
    return {
      title: "Classifying findings",
      detail: "Documents are already stored. Severity is assigned from the evidence collected so far.",
    };
  }
  if (assets > 0) {
    return {
      title: "Reading saved documents",
      detail: "Files inside the scope are in. Metadata extraction and detection run on those files.",
    };
  }
  return {
    title: "Searching the authorized scope",
    detail: "The scan is confirming the scope and looking for public documents to download.",
  };
}

type Props = {
  startedAt: string | null | undefined;
  totalAssets: number;
  totalFindings: number;
  issueCount: number;
  stageLabel: string | null;
  message: string;
  currentAsset: string;
  contractError: boolean;
  /** Step the server just reported, and the pipeline total (SSE event). */
  currentStep: number;
  totalSteps: number;
};

export function LiveActivity({
  startedAt,
  totalAssets,
  totalFindings,
  issueCount,
  stageLabel,
  message,
  currentAsset,
  contractError,
  currentStep,
  totalSteps,
}: Props) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const copy = activityCopy(totalAssets, totalFindings, stageLabel);
  const percent = totalSteps > 0 ? Math.min(100, Math.round((currentStep / totalSteps) * 100)) : 0;

  return (
    <section className="mt-live" aria-label="Scan activity" aria-live="polite">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="mt-kicker">Live scan</p>
          <h2 className="text-base font-semibold text-mt-fg">{copy.title}</h2>
        </div>
        <p className="mt-tech text-lg text-mt-fg">
          <span className="sr-only">Elapsed </span>
          {formatElapsed(startedAt, now)}
        </p>
      </div>
      {/* Real progress: the server's step over the pipeline total. */}
      <div
        className="mt-live-sweep"
        role="progressbar"
        aria-label="Scan progress"
        aria-valuemin={0}
        aria-valuemax={totalSteps}
        aria-valuenow={currentStep}
        aria-valuetext={`Step ${currentStep} of ${totalSteps}`}
      >
        <span style={{ width: `${percent}%` }} />
      </div>
      <p className="text-sm text-mt-muted">{copy.detail}</p>
      <dl className="mt-live-counts">
        <div>
          <dt>Documents</dt>
          <dd>{totalAssets}</dd>
        </div>
        <div>
          <dt>Findings</dt>
          <dd>{totalFindings}</dd>
        </div>
        <div>
          <dt>Asset issues</dt>
          <dd>{issueCount}</dd>
        </div>
      </dl>
      {message ? <p className="mt-tech whitespace-pre-wrap">{message}</p> : null}
      {currentAsset ? <p className="mt-tech break-all">{currentAsset}</p> : null}
      {contractError ? <p className="text-xs text-mt-muted">A progress event could not be read.</p> : null}
    </section>
  );
}
