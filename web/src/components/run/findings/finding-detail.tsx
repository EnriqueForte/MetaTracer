"use client";

import { useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LayerChip } from "@/components/ui/status-chip";
import { severityKey } from "@/lib/api/types";

import { AssetLink } from "./asset-link";
import { FeedbackForm } from "./feedback-form";
import { CONFIDENCE_LABEL, SEVERITY_LABEL, type Finding } from "./model";

type Props = {
  finding: Finding;
  canMutate: boolean;
  extra?: (finding: Finding) => ReactNode;
  onClose?: () => void;
  /** False when a parent already exposes the title (sheet dialog). */
  heading?: boolean;
};

/** Finding card shared by the mobile sheet and the desktop split pane. */
export function FindingDetail({ finding, canMutate, extra, onClose, heading = true }: Props) {
  const [copied, setCopied] = useState(false);

  async function copyEvidence(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      {heading || onClose ? (
        <div className="flex items-start justify-between gap-2">
          {heading ? <h2 className="mt-section-title">{finding.title}</h2> : null}
          {onClose ? (
            <Button variant="secondary" className="shrink-0 px-2 py-1 text-xs" onClick={onClose}>
              Cerrar
            </Button>
          ) : null}
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={severityKey(finding.severity)}>
          {SEVERITY_LABEL[severityKey(finding.severity)]}
        </Badge>
        <span className="text-sm text-mt-fg">{finding.type_label}</span>
        <span className="text-xs text-mt-muted">Confianza</span>
        <Badge variant="confidence">{CONFIDENCE_LABEL[finding.confidence]}</Badge>
      </div>
      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold text-mt-fg">Evidencia</h3>
          <LayerChip layer="observed" />
        </div>
        <pre className="mt-evidence border border-mt-border bg-mt-bg p-3">{finding.evidence_snippet}</pre>
        <p className="text-xs font-semibold text-mt-muted">Campo</p>
        <p className="mt-tech">{finding.field_source}</p>
        <p className="text-xs font-semibold text-mt-muted">URL de origen</p>
        <AssetLink url={finding.asset_source_url} />
        <p className="text-xs font-semibold text-mt-muted">URL final</p>
        <AssetLink url={finding.asset_final_url} />
        <p className="text-xs font-semibold text-mt-muted">Tipo de contenido</p>
        <p className="mt-tech">{finding.asset_content_type}</p>
        <Button
          variant="secondary"
          className="self-start"
          onClick={() => void copyEvidence(finding.evidence_snippet)}
        >
          {copied ? "Copiado" : "Copiar"}
        </Button>
      </section>
      {extra ? extra(finding) : null}
      <section className="flex flex-col gap-3 rounded-md border border-mt-border-strong bg-mt-surface p-3">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-xs font-semibold text-mt-muted">Análisis de IA — no es evidencia</p>
          <LayerChip layer="inferred" />
        </div>
        {finding.severity_justification ? (
          <div>
            <h3 className="text-xs font-semibold text-mt-muted">Justificación</h3>
            <p className="text-sm text-mt-fg">{finding.severity_justification}</p>
          </div>
        ) : null}
        {finding.impact_analysis ? (
          <div>
            <h3 className="text-xs font-semibold text-mt-muted">Impacto</h3>
            <p className="text-sm text-mt-fg">{finding.impact_analysis}</p>
          </div>
        ) : null}
        {finding.reproduction_steps.length > 0 ? (
          <div>
            <h3 className="text-xs font-semibold text-mt-muted">Pasos de reproducción</h3>
            <ol className="flex list-decimal flex-col gap-1 ps-5">
              {finding.reproduction_steps.map((step, index) => (
                <li key={index} className="text-sm text-mt-fg">
                  {step}
                </li>
              ))}
            </ol>
          </div>
        ) : null}
        {finding.remediation_advice ? (
          <div>
            <h3 className="text-xs font-semibold text-mt-muted">Remediación</h3>
            <p className="text-sm text-mt-fg">{finding.remediation_advice}</p>
          </div>
        ) : null}
      </section>
      {canMutate ? <FeedbackForm key={`feedback:${finding.id}`} finding={finding} /> : null}
    </div>
  );
}
