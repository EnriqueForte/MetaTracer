"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

const DEFAULT_MIN = 320;
const DEFAULT_MAX = 720;
const STORAGE_KEY = "mt-panel-width";

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function readStored(min: number, max: number, fallback: number): number {
  if (typeof window === "undefined") return fallback;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  const parsed = raw ? Number.parseInt(raw, 10) : Number.NaN;
  return Number.isFinite(parsed) ? clamp(parsed, min, max) : fallback;
}

type Props = {
  /** The list. It keeps its scroll position and filters when the pane opens. */
  children: ReactNode;
  /** The detail pane, or null when nothing is selected. */
  panel: ReactNode | null;
  panelLabel: string;
  min?: number;
  max?: number;
  defaultWidth?: number;
  /** Below this viewport width the desktop split is not used (the caller renders a Sheet). */
  className?: string;
};

/**
 * Two-column workspace with a persistent, resizable detail pane.
 *
 * The pane is *persistent* on purpose: closing it to look at the next row was
 * the main cost of the old modal. Filters, selection and scroll stay put.
 *
 * Keyboard: the separator takes focus and resizes with ArrowLeft/ArrowRight
 * (Shift for a larger step), Home/End jump to the bounds. The width is stored
 * in `localStorage` so it survives navigation; it is clamped on every read, so
 * a corrupted value can never produce an unusable layout.
 */
export function SplitPane({
  children,
  panel,
  panelLabel,
  min = DEFAULT_MIN,
  max = DEFAULT_MAX,
  defaultWidth = 420,
  className,
}: Props) {
  const [width, setWidth] = useState(defaultWidth);
  const [resizing, setResizing] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setWidth(readStored(min, max, defaultWidth));
  }, [defaultWidth, max, min]);

  const commit = useCallback(
    (next: number) => {
      const clamped = clamp(next, min, max);
      setWidth(clamped);
      try {
        window.localStorage.setItem(STORAGE_KEY, String(clamped));
      } catch {
        /* a full or blocked storage never breaks the layout */
      }
      return clamped;
    },
    [max, min],
  );

  useEffect(() => {
    if (!resizing) return;
    function onMove(event: PointerEvent) {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      // The pane is on the right: its width is the distance from the pointer
      // to the container's right edge.
      commit(rect.right - event.clientX);
    }
    function onUp() {
      setResizing(false);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [commit, resizing]);

  function onKey(event: React.KeyboardEvent<HTMLDivElement>) {
    const step = event.shiftKey ? 64 : 16;
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      commit(width + step);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      commit(width - step);
    } else if (event.key === "Home") {
      event.preventDefault();
      commit(max);
    } else if (event.key === "End") {
      event.preventDefault();
      commit(min);
    }
  }

  return (
    <div
      ref={containerRef}
      className={cn("mt-workspace", className)}
      style={{ ["--mt-panel-width" as string]: `${width}px` }}
    >
      <div className="min-w-0">{children}</div>
      {panel ? (
        <>
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize detail panel"
            aria-valuenow={width}
            aria-valuemin={min}
            aria-valuemax={max}
            tabIndex={0}
            className="mt-split-handle"
            onKeyDown={onKey}
            onPointerDown={(event) => {
              event.preventDefault();
              setResizing(true);
            }}
          />
          <aside className="mt-workspace-panel" aria-label={panelLabel}>
            {panel}
          </aside>
        </>
      ) : null}
    </div>
  );
}

export { DEFAULT_MIN as SPLIT_MIN, DEFAULT_MAX as SPLIT_MAX };
