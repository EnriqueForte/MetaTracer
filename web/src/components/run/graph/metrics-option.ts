import { EXTRACTION_STATUS_LABEL, FINDING_TYPE_LABEL } from "@/lib/ui-copy";
import type { GraphMetrics } from "@/lib/api/graph";

export type BarSeries = {
  title: string;
  labels: string[];
  values: number[];
};

function rows(map: Record<string, number>, labels: Record<string, string>): BarSeries["labels"] {
  return Object.entries(map)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([key]) => labels[key] ?? key);
}

function values(map: Record<string, number>, labels: Record<string, string>): number[] {
  return Object.entries(map)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([, count]) => count);
}

export function metricSeries(metrics: GraphMetrics): BarSeries[] {
  return [
    {
      title: "Por tipo MIME",
      labels: rows(metrics.by_content_type, {}),
      values: values(metrics.by_content_type, {}),
    },
    {
      title: "Por tipo de hallazgo",
      labels: rows(metrics.by_finding_type, FINDING_TYPE_LABEL),
      values: values(metrics.by_finding_type, FINDING_TYPE_LABEL),
    },
    {
      title: "Por estado de extracción",
      labels: rows(metrics.by_extraction_status, EXTRACTION_STATUS_LABEL),
      values: values(metrics.by_extraction_status, EXTRACTION_STATUS_LABEL),
    },
  ].filter((series) => series.values.some((value) => value > 0));
}

export function hasMetricData(metrics: GraphMetrics): boolean {
  return metricSeries(metrics).length > 0;
}
