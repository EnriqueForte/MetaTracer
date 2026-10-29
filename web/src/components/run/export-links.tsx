"use client";

import { useState } from "react";

import { EXPORTS, REDACTIONS, exportHref, type Redaction } from "@/components/run/run-model";
import { Button } from "@/components/ui/button";

export function ExportLinks({ runId }: { runId: string }) {
  const [redact, setRedact] = useState<Redaction>("contacts");
  const titleId = `export-${runId}`;
  return (
    <section className="mt-card flex flex-col gap-3 p-4" aria-labelledby={titleId}>
      <div>
        <h2 id={titleId} className="mt-section-title">
          Download a report
        </h2>
        <p className="mt-1 text-sm text-mt-muted">
          The file includes methodology, coverage, and limitations. Redaction changes this file
          only. Archive indexes are not reported as current exposure.
        </p>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex flex-col gap-1">
          <label htmlFor={`redact-${runId}`} className="text-xs font-semibold text-mt-muted">
            Redaction
          </label>
          <select
            id={`redact-${runId}`}
            value={redact}
            onChange={(event) => setRedact(event.target.value as Redaction)}
            className="rounded-md border border-mt-border-strong bg-mt-bg px-2 py-1 text-xs text-mt-fg"
          >
            {REDACTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        {EXPORTS.map(([format, label]) => (
          <Button key={format} variant="secondary" className="px-2 py-1 text-xs" asChild>
            <a href={exportHref(runId, format, redact)} download>
              {label}
            </a>
          </Button>
        ))}
      </div>
      <p className="text-xs text-mt-muted">The report file is regenerated on the server.</p>
    </section>
  );
}
