"use client";

import { useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { severityKey } from "@/lib/api/types";

import { AssetLink } from "./asset-link";
import { FeedbackForm } from "./feedback-form";
import { CONFIDENCE_LABEL, SEVERITY_LABEL, type Finding } from "./model";

type Props = {
  finding: Finding | null;
  canMutate: boolean;
  onClose: () => void;
  extra?: (finding: Finding) => ReactNode;
};

export function FindingSheet({ finding, canMutate, onClose, extra }: Props) {
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
    <Sheet open={finding !== null} onOpenChange={(open) => { if (!open) onClose(); }}>
      <SheetContent className="w-[min(36rem,100%)] overflow-y-auto">
        {finding ? (
          <div className="flex flex-col gap-6">
            <SheetTitle>{finding.title}</SheetTitle>
            <SheetDescription className="sr-only">{finding.type_label}</SheetDescription>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={severityKey(finding.severity)}>
                {SEVERITY_LABEL[severityKey(finding.severity)]}
              </Badge>
              <span className="text-sm text-mt-fg">{finding.type_label}</span>
              <span className="text-xs text-mt-muted">Confianza</span>
              <Badge variant="confidence">{CONFIDENCE_LABEL[finding.confidence]}</Badge>
            </div>
            <section className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold text-mt-fg">Evidencia</h3>
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
              <p className="text-xs font-semibold text-mt-muted">Análisis de IA — no es evidencia</p>
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
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
