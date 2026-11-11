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
    targets: z.array(z.string()).min(1, "Indica al menos un objetivo."),
    scope_domains: z.array(z.string()),
    scope_ids: z.array(z.string()),
    reasoning_depth: z.enum(DEPTHS),
  })
  .refine((value) => value.scope_domains.length > 0 || value.scope_ids.length > 0, {
    message:
      "Indica al menos un dominio de alcance autorizado o elige un alcance guardado; el alcance nunca se infiere del objetivo.",
  })
  .refine((value) => !(value.scope_domains.length > 0 && value.scope_ids.length > 0), {
    message: "Usa alcances guardados o dominios manuales, no ambos.",
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
      setError(parsed.error.issues[0]?.message ?? "Revisa el formulario del escaneo.");
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
          setError("No se pudo iniciar el escaneo (HTTP 202).");
          setStarting(false);
          setModalOpen(false);
          return;
        }
        window.location.assign(`${BASE_PATH}/runs/${encodeURIComponent(runId)}`);
        return;
      }
      if (response.status === 409) {
        setError("Ya hay otro escaneo en curso; espera a que termine.");
      } else if (response.status === 403) {
        setError("El servidor rechazó la confirmación de alcance.");
      } else if (response.status === 404) {
        setError("El alcance guardado ya no existe; elige otro o escribe los dominios.");
      } else if (response.status === 429) {
        setError("Demasiadas peticiones: espera unos segundos y reintenta.");
      } else if (response.status >= 500) {
        setError("La API falló internamente; reintenta o revisa los registros del servidor.");
      } else {
        setError(`No se pudo iniciar el escaneo (HTTP ${response.status}).`);
      }
    } catch {
      setError("Error de red: la API no está accesible.");
    }
    setStarting(false);
    setModalOpen(false);
  }

  const scopeSummary =
    draft && draft.scope_ids.length > 0
      ? selectedScopes.map((scope) => scope.domains.join(", ")).filter(Boolean).join(", ")
      : (draft?.scope_domains ?? []).join(", ");

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="mt-page-head">
        <div>
          <h1 className="mt-title">Nuevo escaneo</h1>
          <p className="text-sm text-mt-muted">
            Descubre metadatos sensibles (GPS, correos, rutas internas, versiones de software, comentarios
            de depuración) en documentos públicos dentro de tu alcance autorizado.
          </p>
        </div>
      </div>

      {viewer ? (
        <p role="status" className="rounded-md border border-mt-border-strong bg-mt-surface px-3 py-2 text-sm text-mt-fg">
          Las cuentas de visor pueden revisar escaneos, pero no iniciarlos. Pide a un operador.
        </p>
      ) : null}

      <form
        className="mt-wizard-grid"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          openModal();
        }}
      >
        <section className="mt-card flex flex-col gap-3 p-4">
          <p className="mt-kicker">Paso 1</p>
          <h2 className="mt-section-title">Qué pedir</h2>
          <p className="text-sm text-mt-muted">
            URLs o nombres de host públicos que tienes permiso para solicitar. Un objetivo por línea.
            No se descarga nada hasta que confirmes el alcance.
          </p>
          <div className="flex flex-col gap-1">
            <label htmlFor="targets" className="text-xs font-semibold text-mt-muted">
              Objetivos
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
          <p className="mt-kicker">Paso 2</p>
          <h2 className="mt-section-title">Dónde tienes permiso</h2>
          <p className="text-sm text-mt-muted">
            El alcance es una decisión aparte. El producto nunca lo copia de los objetivos. Usa un
            alcance guardado o escribe los dominios.
          </p>
          <div className="flex flex-col gap-1">
            <label htmlFor="scope" className="text-xs font-semibold text-mt-muted">
              Dominios de alcance autorizado
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
            <legend className="text-xs font-semibold text-mt-muted">Alcances guardados</legend>
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
                  Gestionar alcances…
                </a>
              </div>
            ) : (
              <p className="text-xs text-mt-muted">
                Aún no hay alcances guardados —{" "}
                <a href={`${BASE_PATH}/scopes`} className="underline">
                  crear uno
                </a>
                .
              </p>
            )}
          </fieldset>
        </section>

        <section className="mt-card mt-wizard-span flex flex-col gap-3 p-4">
          <p className="mt-kicker">Paso 3</p>
          <h2 className="mt-section-title">Cómo se lee el informe</h2>
          <p className="text-sm text-mt-muted">
            Breve es una ficha corta. Estándar es el valor por defecto. Detallado pide una explicación
            más larga. La severidad sigue saliendo de la rúbrica.
          </p>
          <div className="flex flex-col gap-1 sm:max-w-xs">
            <label htmlFor="depth" className="text-xs font-semibold text-mt-muted">
              Profundidad del razonamiento
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
                  {item === "brief" ? "Breve" : item === "detailed" ? "Detallado" : "Estándar"}
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" className="self-start" disabled={viewer}>
            Iniciar escaneo
          </Button>
        </section>
      </form>
      <p id="scope-source-note" className="text-xs text-mt-muted" aria-live="polite">
        {usingSaved
          ? "Usando alcances guardados: se ignoran los dominios escritos a mano."
          : usingManual
            ? "Usando dominios manuales: se ignoran los alcances guardados."
            : "Elige alcances guardados o escribe dominios. El alcance nunca se infiere de los objetivos."}
      </p>

      <section className="mt-card flex flex-col gap-3 p-4" aria-labelledby="scan-pipeline-title">
        <div>
          <h2 id="scan-pipeline-title" className="mt-section-title">
            Recorrido
          </h2>
          <p className="mt-meta mt-1">
            Al iniciar, la página del escaneo sigue esta cadena en vivo. Un paso se enciende solo
            cuando el servidor lo informa. El paso del modelo clasifica evidencia ya recogida; no
            abre objetivos nuevos.
          </p>
        </div>
        <ol className="mt-stages" aria-label="Cadena del escaneo">
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
          <DialogTitle>Confirmar alcance autorizado</DialogTitle>
          <DialogDescription className="sr-only">
            Revisa los objetivos y el alcance, y confirma la autorización explícita.
          </DialogDescription>
          <div>
            <p className="text-sm text-mt-fg">Vas a auditar:</p>
            <ul className="mt-1 max-h-32 list-inside list-disc overflow-y-auto text-xs text-mt-muted">
              {(draft?.targets ?? []).map((target) => (
                <li key={target}>{target}</li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-sm text-mt-fg">Limitado al alcance autorizado:</p>
            <p className="mt-tech">{scopeSummary}</p>
          </div>
          <p className="text-xs text-mt-muted">
            MetaTracer solo descarga documentos públicos de estos dominios, extrae sus metadatos
            y nunca intenta explotar. Escanear sistemas sin autorización explícita puede ser ilegal
            en tu jurisdicción.
          </p>
          <label className="flex cursor-pointer items-start gap-2">
            <input
              type="checkbox"
              className="mt-1"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
              aria-label="Confirmo que tengo autorización explícita para auditar estos objetivos y que están dentro del alcance indicado"
            />
            <span className="text-sm text-mt-fg">
              Confirmo que tengo autorización explícita para auditar estos objetivos y que están
              dentro del alcance indicado.
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
              Cancelar
            </Button>
            <Button className="flex-1" disabled={!confirmed || starting} onClick={() => void startScan()}>
              {starting ? "Iniciando escaneo…" : "Confirmar e iniciar escaneo"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
