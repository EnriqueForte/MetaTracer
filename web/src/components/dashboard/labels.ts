const TYPE_LABELS: Record<string, string> = {
  gps: "GPS",
  email: "Email",
  internal_path: "Internal path",
  software_version: "Software version",
  debug_comment: "Debug comment",
};

const TYPE_FILL: Record<string, string> = {
  gps: "bg-mt-chart-1",
  email: "bg-mt-chart-2",
  internal_path: "bg-mt-chart-3",
  software_version: "bg-mt-chart-4",
  debug_comment: "bg-mt-chart-5",
};

function typeLabel(type: string): string {
  return TYPE_LABELS[type] ?? type;
}

function typeFill(type: string): string {
  return TYPE_FILL[type] ?? "bg-mt-secondary";
}

export { typeFill, typeLabel };
