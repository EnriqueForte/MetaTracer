"use client";

import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

export type Density = "comfortable" | "compact";

const STORAGE_KEY = "mt-density";

function readStored(): Density {
  if (typeof window === "undefined") return "comfortable";
  return window.localStorage.getItem(STORAGE_KEY) === "compact" ? "compact" : "comfortable";
}

function apply(density: Density) {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-density", density);
}

/**
 * Reading density for the tables and the evidence font.
 *
 * It writes `html[data-density]`, so every table follows without a React
 * re-render (the CSS owns the tokens). The default is comfortable: the brief
 * asks for high legibility, with density available when the analyst wants more
 * rows on screen. The choice persists across pages.
 */
export function DensitySwitch({ className }: { className?: string }) {
  const [density, setDensity] = useState<Density>("comfortable");

  useEffect(() => {
    const stored = readStored();
    apply(stored);
    setDensity(stored);
  }, []);

  function choose(next: Density) {
    setDensity(next);
    apply(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* blocked storage: the choice still applies for this page */
    }
  }

  return (
    <div
      className={cn("inline-flex items-center gap-1", className)}
      role="radiogroup"
      aria-label="Densidad de la tabla"
    >
      <span className="text-xs text-mt-muted">Densidad</span>
      {(["comfortable", "compact"] as const).map((option) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={density === option}
          className="rounded-sm border border-mt-border-strong px-2 py-0.5 text-xs text-mt-muted aria-checked:border-mt-accent aria-checked:bg-mt-accent-soft aria-checked:text-mt-accent-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mt-focus"
          onClick={() => choose(option)}
        >
          {option === "comfortable" ? "Cómoda" : "Compacta"}
        </button>
      ))}
    </div>
  );
}

export { apply as applyDensity };
