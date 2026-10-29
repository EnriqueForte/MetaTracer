"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";

type Props = {
  /** The stored value, exactly as persisted (already sanitized server-side). */
  value: string;
  /** Optional normalized form shown beside the original. */
  normalized?: string | null;
  /** True when the extractor truncated this value. */
  truncated?: boolean;
  label?: string;
};

const PREVIEW_CHARS = 160;

/**
 * One metadata value: the stored text, plus its normalized form when the
 * pipeline knows one (today only GPS) and a visible truncation marker.
 *
 * Rendered as text inside a `<pre>` — never as HTML. The original is never
 * replaced by the normalized form: the analyst must be able to quote what the
 * file actually contained.
 */
export function RawValue({ value, normalized, truncated, label = "Value" }: Props) {
  const [expanded, setExpanded] = useState(false);
  const long = value.length > PREVIEW_CHARS;
  const shown = expanded || !long ? value : `${value.slice(0, PREVIEW_CHARS)}…`;

  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-mt-muted">{label}</span>
        {truncated ? (
          <span className="mt-layer-chip" data-layer="inferred" title="The extractor cut this value at its size ceiling">
            Truncated
          </span>
        ) : null}
      </div>
      <pre className="mt-evidence border border-mt-border bg-mt-bg p-2">{shown}</pre>
      {long ? (
        <Button variant="ghost" className="self-start py-0.5 text-xs" onClick={() => setExpanded((open) => !open)}>
          {expanded ? "Show less" : "Show full value"}
        </Button>
      ) : null}
      {normalized ? (
        <div className="flex flex-col gap-1">
          <span className="text-xs font-semibold text-mt-muted">Normalized</span>
          <p className="mt-tech">{normalized}</p>
        </div>
      ) : null}
    </div>
  );
}
