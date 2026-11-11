"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { severityKey } from "@/lib/api/types";

import { AssetLink } from "./asset-link";
import { groupByAsset, SEVERITY_LABEL, type Finding } from "./model";

type Props = {
  findings: Finding[];
  activeAsset: string;
  onOpen: (finding: Finding) => void;
  onFilterAsset: (asset: string) => void;
};

/** Assets of the filtered list, in API order. Each badge opens its finding. */
export function AssetFindings({ findings, activeAsset, onOpen, onFilterAsset }: Props) {
  const groups = groupByAsset(findings);
  if (groups.length === 0) return null;
  return (
    <details className="mt-card flex min-w-0 flex-col gap-3 p-4">
      <summary className="mt-section-title cursor-pointer">
        <h2 id="asset-findings-title" className="mt-section-title inline">
          Activos con hallazgos
        </h2>{" "}
        <span className="mt-meta inline">({groups.length})</span>
      </summary>
      <ul className="mt-3 flex flex-col gap-3" aria-labelledby="asset-findings-title">
        {groups.map(([url, items]) => (
          <li key={url} className="flex min-w-0 flex-col gap-1 border-t border-mt-border pt-2 first:border-t-0 first:pt-0">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <AssetLink url={url} />
              <Button
                variant="toggle"
                aria-pressed={activeAsset === url}
                onClick={() => onFilterAsset(activeAsset === url ? "" : url)}
              >
                {activeAsset === url ? "Mostrando solo este activo" : "Solo este activo"}
              </Button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {items.map((finding) => (
                <button
                  key={finding.id}
                  type="button"
                  className="rounded-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-mt-focus"
                  onClick={() => onOpen(finding)}
                >
                  <Badge variant={severityKey(finding.severity)}>
                    {finding.type_label} · {SEVERITY_LABEL[severityKey(finding.severity)]}
                  </Badge>
                </button>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </details>
  );
}
