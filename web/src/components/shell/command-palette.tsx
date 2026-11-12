"use client";

import { useQuery } from "@tanstack/react-query";
import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { isGlobalSearch } from "@/components/search/search-view";
import { getJson, hasArray } from "@/lib/api/client";
import type { RunListResponse } from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";
import type { Actor } from "@/lib/session";

export type Command = { id: string; label: string; hint: string; href: string };

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function baseCommands(actor: Actor): Command[] {
  const commands: Command[] = [
    { id: "new-scan", label: "Nuevo escaneo", hint: "Objetivos y alcance", href: "/" },
    { id: "dashboard", label: "Panel", hint: "Resumen", href: "/dashboard" },
    { id: "search", label: "Buscar", hint: "Hallazgos y metadatos", href: "/search" },
    { id: "history", label: "Historial", hint: "Escaneos locales", href: "/runs" },
    { id: "investigations", label: "Investigaciones", hint: "Escaneos agrupados", href: "/investigations" },
    { id: "compare", label: "Comparar escaneos", hint: "Nuevos / resueltos / persistentes", href: "/runs/compare" },
    { id: "scopes", label: "Alcances", hint: "Alcances guardados", href: "/scopes" },
  ];
  if (actor === "operator") {
    commands.push(
      { id: "users", label: "Usuarios", hint: "Cuentas e invitaciones", href: "/users" },
      { id: "integrations", label: "Integraciones", hint: "Conectores de salida", href: "/integrations" },
      { id: "webhooks", label: "Webhooks", hint: "Notificaciones de salida", href: "/webhooks" },
      { id: "knowledge", label: "Conocimiento", hint: "Exportar / importar precedentes", href: "/knowledge" },
    );
  }
  return commands;
}

/** Commands matching the text, plus recent runs by id prefix or target, plus a raw UUID jump. */
export function matchCommands(
  text: string,
  commands: Command[],
  runs: RunListResponse["runs"],
): Command[] {
  const needle = text.trim().toLowerCase();
  const fixed = needle
    ? commands.filter((command) => command.label.toLowerCase().includes(needle))
    : commands;
  const runMatches = needle
    ? runs
        .filter(
          (run) =>
            run.run_id.toLowerCase().startsWith(needle) || run.target.toLowerCase().includes(needle),
        )
        .slice(0, 6)
        .map((run) => ({
          id: `run-${run.run_id}`,
          label: `Abrir escaneo ${run.target}`,
          hint: run.run_id.slice(0, 8),
          href: `/runs/${encodeURIComponent(run.run_id)}`,
        }))
    : [];
  const direct =
    UUID_RE.test(text.trim()) && !runMatches.some((item) => item.id === `run-${text.trim()}`)
      ? [{ id: "run-direct", label: `Abrir escaneo ${text.trim()}`, hint: "Id del escaneo", href: `/runs/${encodeURIComponent(text.trim())}` }]
      : [];
  return [...fixed, ...runMatches, ...direct];
}

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  actor: Actor;
  onNavigate: (href: string) => void;
};

export function CommandPalette({ open, onOpenChange, actor, onNavigate }: Props) {
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const [active, setActive] = useState(0);
  const runs = useQuery({
    queryKey: [...queryKeys.runs, "palette"],
    queryFn: () => getJson<RunListResponse>("/api/runs?limit=50", hasArray("runs")),
    enabled: open,
  });
  const needle = text.trim();
  const evidence = useQuery({
    queryKey: [...queryKeys.globalSearch({ q: needle, kind: "findings", limit: "8" }), "palette"],
    queryFn: () =>
      getJson(
        `/api/search?q=${encodeURIComponent(needle)}&kind=findings&limit=8`,
        isGlobalSearch,
      ),
    enabled: open && needle.length >= 2,
  });
  const options = useMemo(() => {
    const base = matchCommands(text, baseCommands(actor), runs.data?.runs ?? []);
    const hits = (evidence.data?.findings.items ?? []).slice(0, 8).map((hit) => ({
      id: `finding-${hit.id}`,
      label: hit.evidence_snippet,
      hint: hit.type_label,
      href: `/runs/${encodeURIComponent(hit.run_id)}/findings`,
    }));
    return [...base, ...hits];
  }, [actor, evidence.data, runs.data, text]);
  const current = Math.min(active, Math.max(0, options.length - 1));

  function run(option: Command | undefined) {
    if (!option) return;
    onOpenChange(false);
    setText("");
    setActive(0);
    onNavigate(option.href);
  }

  function onKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => (options.length ? (Math.min(index, options.length - 1) + 1) % options.length : 0));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) =>
        options.length ? (Math.min(index, options.length - 1) - 1 + options.length) % options.length : 0,
      );
    } else if (event.key === "Enter") {
      event.preventDefault();
      run(options[current]);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setText("");
          setActive(0);
        }
        onOpenChange(next);
      }}
    >
      <DialogContent
        className="top-24 translate-y-0 p-0"
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          inputRef.current?.focus();
        }}
      >
        <DialogTitle className="sr-only">Paleta de comandos</DialogTitle>
        <DialogDescription className="sr-only">
          Escribe para filtrar. Las flechas mueven, Intro abre, Escape cierra.
        </DialogDescription>
        <input
          ref={inputRef}
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-activedescendant={options[current] ? `${listId}-${options[current].id}` : undefined}
          aria-label="Buscar comandos o escaneos"
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setActive(0);
          }}
          onKeyDown={onKey}
          placeholder="Ir a… (página, evidencia, id de escaneo)"
          className="w-full rounded-t-md border-b border-mt-border bg-transparent px-4 py-3 text-sm text-mt-fg placeholder:text-mt-faint focus:outline-none"
        />
        <ul id={listId} role="listbox" aria-label="Comandos" className="max-h-80 overflow-y-auto p-2">
          {options.length === 0 ? (
            <li className="px-3 py-2 text-sm text-mt-muted">Ningún comando coincide.</li>
          ) : null}
          {options.map((option, index) => (
            <li
              key={option.id}
              id={`${listId}-${option.id}`}
              role="option"
              aria-selected={index === current}
              className="flex cursor-pointer items-center justify-between gap-3 rounded-sm px-3 py-2 text-sm text-mt-fg aria-selected:bg-mt-accent-soft"
              onMouseEnter={() => setActive(index)}
              onClick={() => run(option)}
            >
              <span className="min-w-0 truncate">{option.label}</span>
              <span className="mt-tech text-xs text-mt-muted">{option.hint}</span>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}

export const SHORTCUTS: [string, string][] = [
  ["Ctrl / ⌘ + K", "Abrir la paleta de comandos"],
  ["/", "Enfocar la búsqueda de hallazgos"],
  ["j / k", "Hallazgo siguiente / anterior"],
  ["x", "Seleccionar o quitar el hallazgo activo"],
  ["Intro o Espacio", "Abrir el hallazgo seleccionado"],
  ["[ / ]", "Ensanchar / estrechar el panel de detalle"],
  ["Esc", "Cerrar el panel o diálogo abierto"],
  ["?", "Mostrar esta ayuda"],
];

export function ShortcutsHelp({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Atajos de teclado</DialogTitle>
        <DialogDescription>Los atajos de una tecla se desactivan mientras escribes en un campo.</DialogDescription>
        <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          {SHORTCUTS.map(([keys, label]) => (
            <div key={keys} className="contents">
              <dt className="mt-tech text-mt-fg">{keys}</dt>
              <dd className="m-0 text-mt-muted">{label}</dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  );
}
