"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { truncate } from "@/lib/api/browser";
import { severityKey } from "@/lib/api/types";

import { SEVERITY_LABEL, type Finding } from "./model";

/** Above this many rows only the visible window is rendered. */
export const VIRTUAL_THRESHOLD = 200;
export const ROW_HEIGHT = 36;
const VIEWPORT_HEIGHT = 640;
const OVERSCAN = 8;

type Props = {
  rows: Finding[];
  activeIndex: number;
  onActiveChange: (index: number) => void;
  onOpen: (finding: Finding) => void;
  extraColumn?: { header: string; cell: (finding: Finding) => ReactNode };
};

export function FindingsTable({ rows, activeIndex, onActiveChange, onOpen, extraColumn }: Props) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const virtual = rows.length > VIRTUAL_THRESHOLD;

  const start = virtual ? Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN) : 0;
  const end = virtual
    ? Math.min(rows.length, Math.ceil((scrollTop + VIEWPORT_HEIGHT) / ROW_HEIGHT) + OVERSCAN)
    : rows.length;
  const visible = rows.slice(start, end);

  useEffect(() => {
    if (activeIndex < 0) return;
    const viewport = viewportRef.current;
    if (virtual && viewport) {
      const top = activeIndex * ROW_HEIGHT;
      if (top < viewport.scrollTop || top + ROW_HEIGHT > viewport.scrollTop + VIEWPORT_HEIGHT) {
        viewport.scrollTop = Math.max(0, top - VIEWPORT_HEIGHT / 2);
        setScrollTop(viewport.scrollTop);
      }
    }
    const row = viewport?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`);
    row?.focus();
  }, [activeIndex, virtual]);

  function onRowKey(event: KeyboardEvent<HTMLTableRowElement>, finding: Finding) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onOpen(finding);
    }
  }

  const columns = extraColumn ? 5 : 4;
  const body = (
    <Table>
      <caption className="sr-only">Findings of this scan, in API order</caption>
      <TableHeader>
        <TableRow>
          <TableHead className="px-2 py-1 font-medium tracking-normal normal-case">Severity</TableHead>
          <TableHead className="px-2 py-1 font-medium tracking-normal normal-case">Type</TableHead>
          <TableHead className="px-2 py-1 font-medium tracking-normal normal-case">Evidence</TableHead>
          <TableHead className="px-2 py-1 font-medium tracking-normal normal-case">Asset</TableHead>
          {extraColumn ? (
            <TableHead className="px-2 py-1 font-medium tracking-normal normal-case">
              {extraColumn.header}
            </TableHead>
          ) : null}
        </TableRow>
      </TableHeader>
      <TableBody>
        {virtual && start > 0 ? (
          <tr aria-hidden="true" style={{ height: start * ROW_HEIGHT }}>
            <td colSpan={columns} />
          </tr>
        ) : null}
        {visible.map((finding, offset) => {
          const index = start + offset;
          return (
            <TableRow
              key={finding.id}
              data-index={index}
              tabIndex={0}
              aria-selected={index === activeIndex}
              className="cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-mt-focus aria-selected:bg-mt-accent-soft"
              style={virtual ? { height: ROW_HEIGHT } : undefined}
              onClick={() => {
                onActiveChange(index);
                onOpen(finding);
              }}
              onFocus={() => {
                if (index !== activeIndex) onActiveChange(index);
              }}
              onKeyDown={(event) => onRowKey(event, finding)}
            >
              <TableCell className="px-2 py-1">
                <Badge variant={severityKey(finding.severity)}>
                  {SEVERITY_LABEL[severityKey(finding.severity)]}
                </Badge>
              </TableCell>
              <TableCell className="px-2 py-1">{finding.type_label}</TableCell>
              <TableCell className="mt-tech px-2 py-1">{truncate(finding.evidence_snippet, 90)}</TableCell>
              <TableCell className="mt-tech px-2 py-1">{truncate(finding.asset_final_url, 60)}</TableCell>
              {extraColumn ? <TableCell className="px-2 py-1">{extraColumn.cell(finding)}</TableCell> : null}
            </TableRow>
          );
        })}
        {virtual && end < rows.length ? (
          <tr aria-hidden="true" style={{ height: (rows.length - end) * ROW_HEIGHT }}>
            <td colSpan={columns} />
          </tr>
        ) : null}
      </TableBody>
    </Table>
  );

  if (!virtual) return <div ref={viewportRef}>{body}</div>;
  return (
    <div
      ref={viewportRef}
      className="overflow-y-auto"
      style={{ maxHeight: VIEWPORT_HEIGHT }}
      onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
      data-virtual="true"
    >
      {body}
    </div>
  );
}
