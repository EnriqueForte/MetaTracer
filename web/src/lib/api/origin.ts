export function apiOrigin(): string {
  const raw = process.env.METATRACER_API_ORIGIN ?? "http://127.0.0.1:8000";
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error("METATRACER_API_ORIGIN is not an absolute URL");
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("METATRACER_API_ORIGIN must be http or https");
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error("METATRACER_API_ORIGIN must be an origin only");
  }
  if (url.pathname !== "/" && url.pathname !== "") {
    throw new Error("METATRACER_API_ORIGIN must not include a path");
  }
  return url.origin;
}
