export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail || `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

/** FastAPI `detail`: a string, or a 422 list of `{msg}`. Rendered as text only. */
export function detailText(payload: unknown): string {
  if (!payload || typeof payload !== "object") return "";
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        item && typeof item === "object" && typeof (item as { msg?: unknown }).msg === "string"
          ? (item as { msg: string }).msg
          : "",
      )
      .filter(Boolean);
    return messages.join("; ");
  }
  return "";
}

export async function readDetail(response: Response): Promise<string> {
  try {
    return detailText(await response.json());
  } catch {
    return "";
  }
}
