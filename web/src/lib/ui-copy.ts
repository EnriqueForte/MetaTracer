/** Presentation labels for Web V2. API enum values stay English lowercase. */

export const RUN_STATUS_LABEL = {
  pending: "Pendiente",
  running: "En curso",
  completed: "Completado",
  failed: "Fallido",
  aborted: "Abortado",
} as const;

export const SEVERITY_LABEL = {
  critical: "Crítica",
  high: "Alta",
  medium: "Media",
  low: "Baja",
  info: "Informativa",
  unclassified: "Sin clasificar",
} as const;

export const CONFIDENCE_LABEL = {
  high: "Alta",
  medium: "Media",
  low: "Baja",
} as const;

export const TRIAGE_LABEL = {
  open: "Abierto",
  confirmed: "Confirmado",
  false_positive: "Falso positivo",
  fixed: "Corregido",
} as const;

export const FINDING_TYPE_LABEL: Record<string, string> = {
  gps: "GPS / coordenadas",
  email: "Correo",
  internal_path: "Ruta interna",
  software_version: "Versión de software",
  debug_comment: "Comentario de depuración",
  internal_endpoint: "Endpoint interno",
  cloud_storage: "Almacenamiento en la nube",
};

export const EXTRACTION_STATUS_LABEL: Record<string, string> = {
  ok: "Correcto",
  skipped: "Omitido",
  failed: "Fallido",
};

export const STAGE_LABELS = {
  scope_validation: "Validación de alcance",
  discovery: "Descubrimiento",
  downloading: "Descarga",
  extraction: "Extracción de metadatos",
  detection: "Detección",
  ai_analysis: "Clasificación y análisis con IA",
  report_generation: "Generación del informe",
} as const;

export const EXPORT_LABELS = [
  ["md", "Descargar Markdown"],
  ["json", "Descargar JSON"],
  ["html", "Descargar HTML"],
  ["csv", "Descargar CSV"],
  ["bounty", "Descargar Bounty TXT"],
] as const;

export const REDACTION_LABELS = [
  ["contacts", "Contactos"],
  ["coordinates", "Coordenadas"],
  ["all", "Contactos y coordenadas"],
  ["none", "Ninguna"],
] as const;
