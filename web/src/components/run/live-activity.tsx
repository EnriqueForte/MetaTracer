"use client";

import { useEffect, useState } from "react";

export function formatElapsed(startedAt: string | null | undefined, now: number): string {
  if (!startedAt) return "—";
  const iso = /[zZ]|[+-]\d\d:\d\d$/.test(startedAt) ? startedAt : `${startedAt}Z`;
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return "—";
  const total = Math.max(0, Math.floor((now - at) / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

/** What the operator can see without a live stage event. */
export function activityCopy(assets: number, findings: number, stageLabel: string | null): {
  title: string;
  detail: string;
} {
  if (stageLabel) {
    return {
      title: stageLabel,
      detail: "Este es el paso que acaba de informar el escaneo.",
    };
  }
  if (findings > 0) {
    return {
      title: "Clasificando hallazgos",
      detail: "Los documentos ya están guardados. La severidad se asigna a partir de la evidencia recogida hasta ahora.",
    };
  }
  if (assets > 0) {
    return {
      title: "Leyendo documentos guardados",
      detail: "Los ficheros del alcance ya están dentro. La extracción de metadatos y la detección corren sobre esos ficheros.",
    };
  }
  return {
    title: "Buscando en el alcance autorizado",
    detail: "El escaneo confirma el alcance y busca documentos públicos para descargar.",
  };
}

type Props = {
  startedAt: string | null | undefined;
  totalAssets: number;
  totalFindings: number;
  issueCount: number;
  stageLabel: string | null;
  message: string;
  currentAsset: string;
  contractError: boolean;
  /** Step the server just reported, and the pipeline total (SSE event). */
  currentStep: number;
  totalSteps: number;
};

export function LiveActivity({
  startedAt,
  totalAssets,
  totalFindings,
  issueCount,
  stageLabel,
  message,
  currentAsset,
  contractError,
  currentStep,
  totalSteps,
}: Props) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const copy = activityCopy(totalAssets, totalFindings, stageLabel);
  const percent = totalSteps > 0 ? Math.min(100, Math.round((currentStep / totalSteps) * 100)) : 0;

  return (
    <section className="mt-live" aria-label="Actividad del escaneo" aria-live="polite">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="mt-kicker">Escaneo en vivo</p>
          <h2 className="text-base font-semibold text-mt-fg">{copy.title}</h2>
        </div>
        <p className="mt-tech text-lg text-mt-fg">
          <span className="sr-only">Transcurrido </span>
          {formatElapsed(startedAt, now)}
        </p>
      </div>
      {/* Real progress: the server's step over the pipeline total. */}
      <div
        className="mt-live-sweep"
        role="progressbar"
        aria-label="Progreso del escaneo"
        aria-valuemin={0}
        aria-valuemax={totalSteps}
        aria-valuenow={currentStep}
        aria-valuetext={`Paso ${currentStep} de ${totalSteps}`}
      >
        <span style={{ width: `${percent}%` }} />
      </div>
      <p className="text-sm text-mt-muted">{copy.detail}</p>
      <dl className="mt-live-counts">
        <div>
          <dt>Documentos</dt>
          <dd>{totalAssets}</dd>
        </div>
        <div>
          <dt>Hallazgos</dt>
          <dd>{totalFindings}</dd>
        </div>
        <div>
          <dt>Incidencias de activos</dt>
          <dd>{issueCount}</dd>
        </div>
      </dl>
      {message ? <p className="mt-tech whitespace-pre-wrap">{message}</p> : null}
      {currentAsset ? <p className="mt-tech break-all">{currentAsset}</p> : null}
      {contractError ? <p className="text-xs text-mt-muted">No se pudo leer un evento de progreso.</p> : null}
    </section>
  );
}
