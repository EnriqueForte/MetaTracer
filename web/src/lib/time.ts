/** `2026-09-29 12:00:00` from an ISO timestamp (UTC, no zone suffix). */
export function formatWhen(value: string): string {
  return value.replace("T", " ").replace(/\.\d+/, "").replace("+00:00", "").replace("Z", "");
}

/** Short English relative time: "just now", "5 min ago", "3 h ago", "2 d ago". */
export function formatRelative(value: string, now: number = Date.now()): string {
  const iso = /[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return "";
  const seconds = Math.max(0, Math.round((now - at) / 1000));
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}
