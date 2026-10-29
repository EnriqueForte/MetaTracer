import { Badge } from "@/components/ui/badge";

/** Layer a value came from. Never used to signal severity. */
export type ProvenanceLayer = "observed" | "inferred" | "external";

const LAYER_LABEL: Record<ProvenanceLayer, string> = {
  observed: "Observed",
  inferred: "Inferred",
  external: "External",
};

const LAYER_HINT: Record<ProvenanceLayer, string> = {
  observed: "Read directly from the asset's metadata",
  inferred: "Derived or interpreted from the observed data",
  external: "Retrieved from a third-party source",
};

/**
 * Provenance chip: where a value came from. The label is always visible — the
 * colour is a second channel, never the only one.
 */
export function LayerChip({ layer }: { layer: ProvenanceLayer }) {
  return (
    <span className="mt-layer-chip" data-layer={layer} title={LAYER_HINT[layer]}>
      {LAYER_LABEL[layer]}
    </span>
  );
}

type StatusTone = "ok" | "skipped" | "failed" | "pending";

const TONE_VARIANT: Record<StatusTone, "completed" | "pending" | "failed"> = {
  ok: "completed",
  skipped: "pending",
  failed: "failed",
  pending: "pending",
};

/** Extraction status: text first, colour second. */
export function StatusChip({ tone, label }: { tone: StatusTone; label: string }) {
  return <Badge variant={TONE_VARIANT[tone]}>{label}</Badge>;
}
