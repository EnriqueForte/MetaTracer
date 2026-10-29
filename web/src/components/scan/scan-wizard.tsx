"use client";

import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { z } from "@/lib/validation/zod";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api/browser";
import { getJson, hasArray } from "@/lib/api/client";
import type { ScopeListResponse } from "@/lib/api/types";
import { BASE_PATH } from "@/lib/constants";
import { queryKeys } from "@/lib/query/keys";
import { useActor } from "@/lib/session";
import { STAGE_LABELS, STAGES } from "@/lib/sse/progress";

const DEPTHS = ["brief", "standard", "detailed"] as const;

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

/**
 * Advisory only: the server's ScanRequest stays the authority (TASK-35, ADR-001).
 * `scope_confirmed` is never part of this schema; it is set on the confirm click.
 */
const scanSchema = z
  .object({
    targets: z.array(z.string()).min(1, "Enter at least one target."),
    scope_domains: z.array(z.string()),
    scope_ids: z.array(z.string()),
    reasoning_depth: z.enum(DEPTHS),
  })
  .refine((value) => value.scope_domains.length > 0 || value.scope_ids.length > 0, {
    message:
      "Enter at least one authorized scope domain or choose a saved scope; the scope is never inferred from the target.",
  })
  .refine((value) => !(value.scope_domains.length > 0 && value.scope_ids.length > 0), {
    message: "Use either saved scopes or manual domains, not both.",
  });

type ScanDraft = z.infer<typeof scanSchema>;

export function ScanWizard() {
  const actor = useActor();
  const [targets, setTargets] = useState("");
  const [scopeDomains, setScopeDomains] = useState("");
  const [depth, setDepth] = useState<(typeof DEPTHS)[number]>("standard");
  const [selectedScopeIds, setSelectedScopeIds] = useState<string[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState<ScanDraft | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  const scopesQuery = useQuery({
    queryKey: queryKeys.scopes,
    queryFn: () => getJson<ScopeListResponse>("/api/scopes", hasArray("scopes")),
  });
  const savedScopes = scopesQuery.data?.scopes ?? [];
  const activeScopeIds = selectedScopeIds.filter((id) => savedScopes.some((scope) => scope.id === id));

  const targetList = lines(targets);
  const manualDomains = domains(scopeDomains);
  const usingSaved = activeScopeIds.length > 0;
  const usingManual = !usingSaved && manualDomains.length > 0;
  const selectedScopes = savedScopes.filter((scope) => activeScopeIds.includes(scope.id));
  const viewer = actor === "viewer";

  function openModal() {
    setError("");
    const parsed = scanSchema.safeParse({
      targets: targetList,
      scope_domains: usingSaved ? [] : manualDomains,
      scope_ids: activeScopeIds,
      reasoning_depth: depth,
    });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Check the scan form.");
      return;
    }
    setDraft(parsed.data);
    setConfirmed(false);
    setModalOpen(true);
  }

  async function startScan() {
    if (!confirmed || !draft) return;
    setStarting(true);
    setError("");
    const body: Record<string, unknown> = {
      targets: draft.targets,
      scope_confirmed: true,
      reasoning_depth: draft.reasoning_depth,
    };
    if (draft.scope_ids.length > 0) body.scope_ids = draft.scope_ids;
    else body.scope_domains = draft.scope_domains;
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
          setModalOpen(false);
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
    setModalOpen(false);
  }

  const scopeSummary =
    draft && draft.scope_ids.length > 0
      ? selectedScopes.map((scope) => scope.domains.join(", ")).filter(Boolean).join(", ")
      : (draft?.scope_domains ?? []).join(", ");

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div>
        <h1 className="mt-title">New scan</h1>
        <p className="text-sm text-mt-muted">
          Discover sensitive metadata (GPS, emails, internal paths, software versions, debug comments)
          in publicly available documents inside your authorized scope.
        </p>
      </div>

      {viewer ? (
        <p role="status" className="rounded-md border border-mt-border-strong bg-mt-surface px-3 py-2 text-sm text-mt-fg">
          Viewer accounts can review runs but cannot start scans. Ask an operator.
        </p>
      ) : null}

      <form
        className="grid grid-cols-1 gap-3"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          openModal();
        }}
      >
        <section className="mt-card flex flex-col gap-3 p-4">
          <p className="mt-kicker">Step 1</p>
          <h2 className="mt-section-title">What to fetch</h2>
          <p className="text-sm text-mt-muted">
            Public URLs or hostnames you are allowed to request. One target per line. Nothing is
            downloaded until you confirm the scope.
          </p>
          <div className="flex flex-col gap-1">
            <label htmlFor="targets" className="text-xs font-semibold text-mt-muted">
              Targets
            </label>
            <textarea
              id="targets"
              rows={3}
              value={targets}
              disabled={viewer}
              onChange={(event) => setTargets(event.target.value)}
              className="mt-tech w-full resize-y rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg placeholder:text-mt-faint focus:border-mt-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mt-focus disabled:opacity-[0.45]"
              placeholder="https://example.com/&#10;files.example.com"
            />
          </div>
        </section>

        <section className="mt-card flex flex-col gap-3 p-4">
          <p className="mt-kicker">Step 2</p>
          <h2 className="mt-section-title">Where you are allowed</h2>
          <p className="text-sm text-mt-muted">
            The scope is a separate decision. The product never copies it from the targets. Use a
            saved scope or type the domains.
          </p>
          <div className="flex flex-col gap-1">
            <label htmlFor="scope" className="text-xs font-semibold text-mt-muted">
              Authorized scope domains
            </label>
            <Input
              id="scope"
              type="text"
              value={scopeDomains}
              disabled={viewer || usingSaved}
              aria-describedby={usingSaved ? "scope-source-note" : "scope-source-note"}
              onChange={(event) => setScopeDomains(event.target.value)}
              className="mt-tech disabled:opacity-[0.45]"
              placeholder="example.com, static.example.com"
            />
          </div>
          <fieldset className="flex flex-col gap-2" disabled={viewer || usingManual}>
            <legend className="text-xs font-semibold text-mt-muted">Saved scopes</legend>
            {savedScopes.length > 0 ? (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                {savedScopes.map((scope) => (
                  <label key={scope.id} className="flex cursor-pointer items-center gap-2">
                    <input
                      type="checkbox"
                      checked={activeScopeIds.includes(scope.id)}
                      aria-describedby={usingManual ? "scope-source-note" : undefined}
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
              <p className="text-xs text-mt-muted">
                No saved scopes yet —{" "}
                <a href={`${BASE_PATH}/scopes`} className="underline">
                  create one
                </a>
                .
              </p>
            )}
          </fieldset>
        </section>

        <section className="mt-card flex flex-col gap-3 p-4">
          <p className="mt-kicker">Step 3</p>
          <h2 className="mt-section-title">How the write-up reads</h2>
          <p className="text-sm text-mt-muted">
            Brief is a short card. Standard is the default. Detailed asks the analyst for a longer
            explanation. Severity still comes from the rubric.
          </p>
          <div className="flex flex-col gap-1 sm:max-w-xs">
            <label htmlFor="depth" className="text-xs font-semibold text-mt-muted">
              Reasoning depth
            </label>
            <select
              id="depth"
              value={depth}
              disabled={viewer}
              onChange={(event) => {
                const next = DEPTHS.find((item) => item === event.target.value);
                if (next) setDepth(next);
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
          <Button type="submit" className="self-start" disabled={viewer}>
            Start scan
          </Button>
        </section>
      </form>
      <p id="scope-source-note" className="text-xs text-mt-muted" aria-live="polite">
        {usingSaved
          ? "Using saved scopes — manual domains are ignored."
          : usingManual
            ? "Using manual domains — saved scopes are ignored."
            : "Choose saved scopes or type domains. The scope is never inferred from the targets."}
      </p>

      <section className="mt-card flex flex-col gap-3 p-4" aria-labelledby="scan-pipeline-title">
        <div>
          <h2 id="scan-pipeline-title" className="mt-section-title">
            Trace
          </h2>
          <p className="mt-meta mt-1">
            After you start, the run page follows this chain live. A step lights only when the
            server reports it. The model step classifies evidence already collected; it does not
            open new targets.
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

      <Dialog open={modalOpen} onOpenChange={(open) => { if (!starting) setModalOpen(open); }}>
        <DialogContent
          className="flex flex-col gap-4"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            cancelRef.current?.focus();
          }}
        >
          <DialogTitle>Confirm authorized scope</DialogTitle>
          <DialogDescription className="sr-only">
            Review the targets and scope, then confirm explicit authorization.
          </DialogDescription>
          <div>
            <p className="text-sm text-mt-fg">You are about to audit:</p>
            <ul className="mt-1 max-h-32 list-inside list-disc overflow-y-auto text-xs text-mt-muted">
              {(draft?.targets ?? []).map((target) => (
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
              ref={cancelRef}
              id="scope-modal-cancel"
              variant="secondary"
              className="flex-1"
              onClick={() => setModalOpen(false)}
            >
              Cancel
            </Button>
            <Button className="flex-1" disabled={!confirmed || starting} onClick={() => void startScan()}>
              {starting ? "Starting scan…" : "Confirm and start scan"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
