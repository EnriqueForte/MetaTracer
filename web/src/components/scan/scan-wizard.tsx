"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api/browser";
import { BASE_PATH } from "@/lib/constants";
import { STAGE_LABELS, STAGES } from "@/lib/sse/progress";

const DEPTHS = ["brief", "standard", "detailed"] as const;

type SavedScope = {
  id: string;
  name: string;
  domains: string[];
  total_domains: number;
};

function lines(value: string): string[] {
  return value
    .split(/\n+/)
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function domains(value: string): string[] {
  return value
    .split(/[\n,]+/)
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function parseScopes(value: unknown): SavedScope[] {
  if (!value || typeof value !== "object") return [];
  const rows = (value as { scopes?: unknown }).scopes;
  if (!Array.isArray(rows)) return [];
  const scopes: SavedScope[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const scope = row as Record<string, unknown>;
    if (typeof scope.id !== "string" || typeof scope.name !== "string") continue;
    if (!Array.isArray(scope.domains) || !scope.domains.every((item) => typeof item === "string")) {
      continue;
    }
    scopes.push({
      id: scope.id,
      name: scope.name,
      domains: scope.domains,
      total_domains: typeof scope.total_domains === "number" ? scope.total_domains : scope.domains.length,
    });
  }
  return scopes;
}

export function ScanWizard() {
  const [targets, setTargets] = useState("");
  const [scopeDomains, setScopeDomains] = useState("");
  const [depth, setDepth] = useState<(typeof DEPTHS)[number]>("standard");
  const [savedScopes, setSavedScopes] = useState<SavedScope[]>([]);
  const [selectedScopeIds, setSelectedScopeIds] = useState<string[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const lastFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const response = await apiFetch("/api/scopes");
        if (!response.ok || cancelled) return;
        const scopes = parseScopes(await response.json());
        if (cancelled) return;
        setSavedScopes(scopes);
        setSelectedScopeIds((current) => current.filter((id) => scopes.some((scope) => scope.id === id)));
      } catch {
        if (!cancelled) setSavedScopes([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!modalOpen) return;
    const cancel = document.getElementById("scope-modal-cancel");
    if (cancel instanceof HTMLElement) cancel.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeModal();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [modalOpen]);

  const targetList = lines(targets);
  const manualDomains = domains(scopeDomains);
  const selectedScopes = savedScopes.filter((scope) => selectedScopeIds.includes(scope.id));

  function closeModal() {
    setModalOpen(false);
    lastFocused.current?.focus();
  }

  function openModal() {
    setError("");
    if (targetList.length === 0) {
      setError("Enter at least one target.");
      return;
    }
    if (manualDomains.length === 0 && selectedScopeIds.length === 0) {
      setError(
        "Enter at least one authorized scope domain or choose a saved scope; the scope is never inferred from the target.",
      );
      return;
    }
    setConfirmed(false);
    lastFocused.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setModalOpen(true);
  }

  async function startScan() {
    if (!confirmed) return;
    setStarting(true);
    setError("");
    const body: {
      targets: string[];
      scope_confirmed: true;
      reasoning_depth: (typeof DEPTHS)[number];
      scope_ids?: string[];
      scope_domains?: string[];
    } = {
      targets: targetList,
      scope_confirmed: true,
      reasoning_depth: depth,
    };
    if (selectedScopeIds.length > 0) {
      body.scope_ids = selectedScopeIds;
    } else {
      body.scope_domains = manualDomains;
    }
    try {
      const response = await apiFetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (response.status === 202) {
        const payload: unknown = await response.json();
        const runId =
          payload && typeof payload === "object" && typeof (payload as { run_id?: unknown }).run_id === "string"
            ? (payload as { run_id: string }).run_id
            : "";
        if (!runId) {
          setError("The scan could not be started (HTTP 202).");
          setStarting(false);
          closeModal();
          return;
        }
        window.location.assign(`${BASE_PATH}/runs/${encodeURIComponent(runId)}`);
        return;
      }
      if (response.status === 409) {
        setError("Another scan is already running; wait for it to finish.");
      } else if (response.status === 403) {
        setError("The scope confirmation was rejected by the server.");
      } else if (response.status === 404) {
        setError("The selected saved scope no longer exists; choose or enter domains manually.");
      } else if (response.status === 429) {
        setError("Too many requests: the API asked us to slow down; retry in a few seconds.");
      } else if (response.status >= 500) {
        setError("The API failed internally; retry, or check the server logs.");
      } else {
        setError(`The scan could not be started (HTTP ${response.status}).`);
      }
    } catch {
      setError("Network error: the API is unreachable.");
    }
    setStarting(false);
    closeModal();
  }

  const scopeSummary =
    selectedScopes.length > 0
      ? selectedScopes.map((scope) => scope.domains.join(", ")).filter(Boolean).join(", ")
      : manualDomains.join(", ");

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div>
        <h1 className="mt-title">New scan</h1>
        <p className="text-sm text-mt-muted">
          Discover sensitive metadata (GPS, emails, internal paths, software versions, debug comments)
          in publicly available documents inside your authorized scope.
        </p>
      </div>

      <form
        className="mt-command"
        onSubmit={(event) => {
          event.preventDefault();
          openModal();
        }}
      >
        <div className="mt-command-field">
          <label htmlFor="targets" className="text-xs text-mt-muted">
            Targets
          </label>
          <textarea
            id="targets"
            rows={1}
            value={targets}
            onChange={(event) => setTargets(event.target.value)}
            className="mt-tech w-full resize-y rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg placeholder:text-mt-faint focus:border-mt-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mt-focus"
            placeholder="One target per line"
          />
        </div>
        <div className="mt-command-field">
          <label htmlFor="scope" className="text-xs text-mt-muted">
            Authorized scope domains
          </label>
          <Input
            id="scope"
            type="text"
            value={scopeDomains}
            onChange={(event) => setScopeDomains(event.target.value)}
            className="mt-tech"
            placeholder="example.com, static.example.com"
          />
        </div>
        <fieldset className="mt-command-field">
          <legend className="text-xs text-mt-muted">Saved scopes</legend>
          {savedScopes.length > 0 ? (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              {savedScopes.map((scope) => (
                <label key={scope.id} className="flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selectedScopeIds.includes(scope.id)}
                    onChange={(event) => {
                      setSelectedScopeIds((current) =>
                        event.target.checked
                          ? [...current, scope.id]
                          : current.filter((id) => id !== scope.id),
                      );
                    }}
                  />
                  <span className="text-sm text-mt-fg">
                    {scope.name}{" "}
                    <span className="text-xs text-mt-muted">({scope.total_domains})</span>
                  </span>
                </label>
              ))}
              <a href={`${BASE_PATH}/scopes`} className="text-xs text-mt-muted underline">
                Manage scopes…
              </a>
            </div>
          ) : (
            <p className="py-2 text-xs text-mt-muted">
              No saved scopes yet —{" "}
              <a href={`${BASE_PATH}/scopes`} className="underline">
                create one
              </a>
              .
            </p>
          )}
        </fieldset>
        <div className="mt-command-field mt-command-depth">
          <label htmlFor="depth" className="text-xs text-mt-muted">
            Reasoning depth
          </label>
          <select
            id="depth"
            value={depth}
            onChange={(event) => {
              const next = event.target.value;
              if (next === "brief" || next === "standard" || next === "detailed") setDepth(next);
            }}
            className="w-full rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg focus:border-mt-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mt-focus"
          >
            {DEPTHS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>
        <Button type="submit" className="mt-command-start">
          Start scan
        </Button>
      </form>
      <p className="text-xs text-mt-muted">
        Only when you are not using a saved scope. The scope is never inferred from the targets.
      </p>

      <section className="mt-card flex flex-col gap-3 p-4" aria-labelledby="scan-pipeline-title">
        <div>
          <h2 id="scan-pipeline-title" className="mt-section-title">
            Trace
          </h2>
          <p className="mt-meta mt-1">
            After you start, this chain follows the live scan. A step lights only when the server
            reports it. The model step classifies evidence already collected; it does not open new
            targets.
          </p>
        </div>
        <ol className="mt-stages" aria-label="Scan pipeline">
          {STAGES.map((key) => (
            <li key={key} className="mt-stage" data-state="pending" data-stage={key}>
              <span className="mt-stage-line" aria-hidden="true" />
              <span className="mt-stage-node">
                <span className="mt-stage-dot" aria-hidden="true" />
                <span>{STAGE_LABELS[key]}</span>
              </span>
            </li>
          ))}
        </ol>
      </section>

      {error ? (
        <p role="alert" className="rounded-md border border-mt-danger-border bg-mt-danger-bg px-3 py-2 text-sm text-mt-danger">
          {error}
        </p>
      ) : null}

      {modalOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-mt-overlay p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="scope-modal-title"
        >
          <div className="flex w-full max-w-lg flex-col gap-4 rounded-md border border-mt-border bg-mt-surface p-4 shadow-mt-overlay">
            <h2 id="scope-modal-title" className="mt-title">
              Confirm authorized scope
            </h2>
            <div>
              <p className="text-sm text-mt-fg">You are about to audit:</p>
              <ul className="mt-1 max-h-32 list-inside list-disc overflow-y-auto text-xs text-mt-muted">
                {targetList.map((target) => (
                  <li key={target}>{target}</li>
                ))}
              </ul>
            </div>
            <div>
              <p className="text-sm text-mt-fg">Restricted to the authorized scope:</p>
              <p className="mt-tech">{scopeSummary}</p>
            </div>
            <p className="text-xs text-mt-muted">
              MetaTracer only downloads public documents on these domains, extracts their metadata
              and never attempts exploitation. Scanning systems without explicit authorization may
              be illegal in your jurisdiction.
            </p>
            <label className="flex cursor-pointer items-start gap-2">
              <input
                type="checkbox"
                className="mt-1"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
                aria-label="I confirm I have explicit authorization to audit these targets and that they are inside the stated scope"
              />
              <span className="text-sm text-mt-fg">
                I confirm I have explicit authorization to audit these targets and that they are
                inside the stated scope.
              </span>
            </label>
            <div className="flex gap-2">
              <Button
                id="scope-modal-cancel"
                variant="secondary"
                className="flex-1"
                onClick={closeModal}
              >
                Cancel
              </Button>
              <Button className="flex-1" disabled={!confirmed || starting} onClick={() => void startScan()}>
                {starting ? "Starting scan…" : "Confirm and start scan"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
