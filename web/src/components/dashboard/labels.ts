import { FINDING_TYPE_LABEL } from "@/lib/ui-copy";

const TYPE_LABELS: Record<string, string> = FINDING_TYPE_LABEL;

const TYPE_FILL: Record<string, string> = {
  gps: "bg-mt-chart-1",
  email: "bg-mt-chart-2",
  internal_path: "bg-mt-chart-3",
  software_version: "bg-mt-chart-4",
  debug_comment: "bg-mt-chart-5",
  internal_endpoint: "bg-mt-chart-1",
  cloud_storage: "bg-mt-chart-2",
};

function typeLabel(type: string): string {
  return TYPE_LABELS[type] ?? type;
}

function typeFill(type: string): string {
  return TYPE_FILL[type] ?? "bg-mt-secondary";
}

export { typeFill, typeLabel };
