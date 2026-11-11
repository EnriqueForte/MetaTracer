/** `2026-09-29 12:00:00` from an ISO timestamp (UTC, no zone suffix). */
export function formatWhen(value: string): string {
  return value.replace("T", " ").replace(/\.\d+/, "").replace("+00:00", "").replace("Z", "");
}

/** Tiempo relativo corto: "ahora", "hace 5 min", "hace 3 h", "hace 2 d". */
export function formatRelative(value: string, now: number = Date.now()): string {
  const iso = /[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return "";
  const seconds = Math.max(0, Math.round((now - at) / 1000));
  if (seconds < 45) return "ahora";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `hace ${hours} h`;
  return `hace ${Math.round(hours / 24)} d`;
}
