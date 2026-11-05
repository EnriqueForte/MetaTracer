"use client";

import { useQuery } from "@tanstack/react-query";
import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { getJson, hasArray } from "@/lib/api/client";
import type { RunListResponse } from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";
import type { Actor } from "@/lib/session";

export type Command = { id: string; label: string; hint: string; href: string };

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function baseCommands(actor: Actor): Command[] {
  const commands: Command[] = [
    { id: "new-scan", label: "New scan", hint: "Targets and scope", href: "/" },
    { id: "dashboard", label: "Dashboard", hint: "Overview", href: "/dashboard" },
    { id: "history", label: "History", hint: "Local runs", href: "/runs" },
    { id: "investigations", label: "Investigations", hint: "Grouped runs", href: "/investigations" },
    { id: "compare", label: "Compare runs", hint: "New / resolved / persistent", href: "/runs/compare" },
    { id: "scopes", label: "Scopes", hint: "Saved scopes", href: "/scopes" },
  ];
  if (actor === "operator") {
    commands.push(
      { id: "users", label: "Users", hint: "Accounts and invitations", href: "/users" },
      { id: "webhooks", label: "Webhooks", hint: "Outbound notifications", href: "/webhooks" },
      { id: "knowledge", label: "Knowledge", hint: "Export / import precedents", href: "/knowledge" },
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
          label: `Open run ${run.target}`,
          hint: run.run_id.slice(0, 8),
          href: `/runs/${encodeURIComponent(run.run_id)}`,
        }))
    : [];
  const direct =
    UUID_RE.test(text.trim()) && !runMatches.some((item) => item.id === `run-${text.trim()}`)
      ? [{ id: "run-direct", label: `Open run ${text.trim()}`, hint: "Run id", href: `/runs/${encodeURIComponent(text.trim())}` }]
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
  const options = useMemo(
    () => matchCommands(text, baseCommands(actor), runs.data?.runs ?? []),
    [actor, runs.data, text],
  );
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
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        <DialogDescription className="sr-only">
          Type to filter. Arrow keys move, Enter opens, Escape closes.
        </DialogDescription>
        <input
          ref={inputRef}
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-activedescendant={options[current] ? `${listId}-${options[current].id}` : undefined}
          aria-label="Search commands or runs"
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setActive(0);
          }}
          onKeyDown={onKey}
          placeholder="Go to… (page, run id or target)"
          className="w-full rounded-t-md border-b border-mt-border bg-transparent px-4 py-3 text-sm text-mt-fg placeholder:text-mt-faint focus:outline-none"
        />
        <ul id={listId} role="listbox" aria-label="Commands" className="max-h-80 overflow-y-auto p-2">
          {options.length === 0 ? (
            <li className="px-3 py-2 text-sm text-mt-muted">No matching command.</li>
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
  ["Ctrl / ⌘ + K", "Open the command palette"],
  ["/", "Focus the findings search"],
  ["j / k", "Next / previous finding"],
  ["x", "Select or unselect the active finding"],
  ["Enter or Space", "Open the selected finding"],
  ["Esc", "Close the open panel or dialog"],
  ["?", "Show this help"],
];

export function ShortcutsHelp({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Keyboard shortcuts</DialogTitle>
        <DialogDescription>Single-key shortcuts are off while you type in a field.</DialogDescription>
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
