import { apiFetch } from "@/lib/api/browser";
import { ApiError, readDetail } from "@/lib/api/errors";
import type { components } from "@/lib/api/generated/schema";

type Schemas = components["schemas"];

export type AssetResponse = Schemas["AssetResponse"];
export type AssetListResponse = Schemas["AssetListResponse"];
export type MetadataItemResponse = Schemas["MetadataItemResponse"];
export type MetadataListResponse = Schemas["MetadataListResponse"];
export type CoverageResponse = Schemas["CoverageResponse"];

/** Query the metadata explorer can send. Unknown params are dropped by the caller. */
export type MetadataQuery = {
  namespace?: string;
  key?: string;
  q?: string;
  asset?: string;
  cursor?: string | null;
};

function query(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(name, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

/**
 * Shape guards, not full schema validation: enough that the UI never renders
 * `undefined` as an empty cell. The lists are the only thing every page needs.
 */
function hasAssetList(value: unknown): value is AssetListResponse {
  return (
    isObject(value) &&
    Array.isArray(value.assets) &&
    typeof value.total === "number" &&
    typeof value.run_id === "string"
  );
}

function hasMetadataList(value: unknown): value is MetadataListResponse {
  return (
    isObject(value) &&
    Array.isArray(value.items) &&
    typeof value.total === "number" &&
    typeof value.run_id === "string"
  );
}

function hasCoverage(value: unknown): value is CoverageResponse {
  return (
    isObject(value) &&
    typeof value.total_assets === "number" &&
    typeof value.ok === "number" &&
    typeof value.counters_recorded === "boolean"
  );
}

async function getJson<T>(path: string, guard: (value: unknown) => value is T): Promise<T> {
  const response = await apiFetch(path);
  if (!response.ok) {
    if (response.status === 404) {
      throw new ApiError(404, "Este escaneo o activo no existe.");
    }
    throw new ApiError(response.status, await readDetail(response));
  }
  const payload: unknown = await response.json();
  if (!guard(payload)) throw new ApiError(response.status, "unexpected response");
  return payload;
}

export function fetchAssets(
  runId: string,
  options: { status?: string; contentType?: string; q?: string; cursor?: string | null; limit?: number } = {},
): Promise<AssetListResponse> {
  const params = query({
    status: options.status,
    content_type: options.contentType,
    q: options.q,
    cursor: options.cursor,
    limit: options.limit ?? 50,
  });
  return getJson(
    `/api/runs/${encodeURIComponent(runId)}/assets${params}`,
    hasAssetList,
  );
}

/** Run-wide metadata, or one asset's metadata when `assetId` is given. */
export function fetchMetadata(
  runId: string,
  options: MetadataQuery & { limit?: number } = {},
  assetId?: string,
): Promise<MetadataListResponse> {
  const params = query({
    namespace: options.namespace,
    key: options.key,
    q: options.q,
    cursor: options.cursor,
    limit: options.limit ?? 100,
  });
  const base = assetId
    ? `/api/runs/${encodeURIComponent(runId)}/assets/${encodeURIComponent(assetId)}/metadata`
    : `/api/runs/${encodeURIComponent(runId)}/metadata`;
  return getJson(`${base}${params}`, hasMetadataList);
}

export function fetchCoverage(runId: string): Promise<CoverageResponse> {
  return getJson(`/api/runs/${encodeURIComponent(runId)}/coverage`, hasCoverage);
}

/** Human label for an extraction status (wire values stay lowercase). */
export const EXTRACTION_LABEL: Record<string, string> = {
  ok: "Extraído",
  skipped: "Omitido",
  failed: "Fallido",
};

/** Human label for a skip reason; unknown values fall back to the raw token. */
export const SKIP_REASON_LABEL: Record<string, string> = {
  unsupported_type: "Tipo no admitido",
  too_large: "Demasiado grande",
  out_of_scope: "Fuera de alcance",
  duplicate_hash: "Contenido duplicado",
  empty_body: "Cuerpo vacío",
  robots_disallow: "Omitido por robots.txt",
};

/** Compact content type for the table (`image/jpeg` stays, long ones shorten). */
export function shortType(contentType: string): string {
  const base = contentType.split(";", 1)[0]?.trim() ?? "";
  if (!base) return "desconocido";
  const map: Record<string, string> = {
    "application/pdf": "PDF",
    "text/html": "HTML",
    "application/xhtml+xml": "HTML",
    "application/javascript": "JS",
    "text/javascript": "JS",
    "application/octet-stream": "binario",
  };
  if (map[base]) return map[base];
  if (base.startsWith("image/")) return base.slice("image/".length).toUpperCase();
  return base;
}

/** Bytes as a compact, tabular-friendly string. */
export function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  const digits = unit === 0 || size >= 100 ? 0 : 1;
  return `${size.toFixed(digits)} ${units[unit]}`;
}

/** Short hash for the table; the full value stays in the detail panel title. */
export function shortHash(hash: string): string {
  return hash ? hash.slice(0, 12) : "—";
}
