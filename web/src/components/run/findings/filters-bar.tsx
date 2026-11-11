"use client";

import type { RefObject } from "react";

import { Button } from "@/components/ui/button";
import { truncate } from "@/lib/api/browser";
import type { SeverityKey } from "@/lib/api/types";

import {
  CONFIDENCE_LABEL,
  CONFIDENCE_LEVELS,
  SEVERITY_FILTERS,
  SEVERITY_LABEL,
  TRIAGE_LABEL,
  TRIAGE_STATUSES,
  type Filters,
} from "./model";

type Props = {
  filters: Filters;
  onChange: (next: Filters) => void;
  total: number;
  counts: Record<SeverityKey, number>;
  types: { value: string; label: string }[];
  dismissed: number;
  searchRef: RefObject<HTMLInputElement | null>;
};

export function FiltersBar({ filters, onChange, total, counts, types, dismissed, searchRef }: Props) {
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });
  return (
    <div className="flex flex-col gap-2" role="group" aria-label="Filtros de hallazgos">
      <div className="flex flex-wrap gap-2">
        <Button
          variant="toggle"
          aria-pressed={filters.severity === "all"}
          onClick={() => set({ severity: "all" })}
        >
          Todos ({total})
        </Button>
        {SEVERITY_FILTERS.map((severity) => (
          <Button
            key={severity}
            variant="toggle"
            aria-pressed={filters.severity === severity}
            onClick={() => set({ severity: filters.severity === severity ? "all" : severity })}
          >
            {SEVERITY_LABEL[severity]} ({counts[severity]})
          </Button>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="toggle" aria-pressed={filters.type === "all"} onClick={() => set({ type: "all" })}>
          Todos los tipos
        </Button>
        {types.map((type) => (
          <Button
            key={type.value}
            variant="toggle"
            aria-pressed={filters.type === type.value}
            onClick={() => set({ type: filters.type === type.value ? "all" : type.value })}
          >
            {type.label}
          </Button>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="toggle"
          aria-pressed={filters.confidence === "all"}
          onClick={() => set({ confidence: "all" })}
        >
          Toda confianza
        </Button>
        {CONFIDENCE_LEVELS.map((level) => (
          <Button
            key={level}
            variant="toggle"
            aria-pressed={filters.confidence === level}
            onClick={() => set({ confidence: filters.confidence === level ? "all" : level })}
          >
            {CONFIDENCE_LABEL[level]}
          </Button>
        ))}
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Filtro de triaje">
        <Button
          variant="toggle"
          aria-pressed={filters.triage === "any"}
          onClick={() => set({ triage: "any" })}
        >
          Cualquier estado
        </Button>
        {TRIAGE_STATUSES.map((status) => (
          <Button
            key={status}
            variant="toggle"
            aria-pressed={filters.triage === status}
            onClick={() => set({ triage: filters.triage === status ? "any" : status })}
          >
            {TRIAGE_LABEL[status]}
          </Button>
        ))}
        <Button
          variant="toggle"
          aria-pressed={filters.dismissed}
          disabled={filters.triage !== "any"}
          onClick={() => set({ dismissed: !filters.dismissed })}
        >
          Mostrar descartados ({dismissed})
        </Button>
      </div>
      {filters.asset ? (
        <div className="flex flex-wrap items-center gap-2 text-xs text-mt-muted">
          <span>Activo</span>
          <span className="mt-tech">{truncate(filters.asset, 80)}</span>
          <Button variant="ghost" className="py-0.5 text-xs" onClick={() => set({ asset: "" })}>
            Quitar filtro de activo
          </Button>
        </div>
      ) : null}
      <label className="sr-only" htmlFor="findings-search">
        Buscar hallazgos
      </label>
      <input
        ref={searchRef}
        id="findings-search"
        type="search"
        value={filters.q}
        onChange={(event) => set({ q: event.target.value })}
        placeholder="Buscar evidencia, título, campo o URL (pulsa / para enfocar)"
        className="w-full rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg placeholder:text-mt-faint focus:border-mt-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mt-focus"
      />
    </div>
  );
}
