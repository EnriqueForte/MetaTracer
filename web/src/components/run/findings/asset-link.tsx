import { safeUrl } from "@/lib/security/safe-url";

/** Link only when the URL is http(s); otherwise show the raw value as text. */
export function AssetLink({ url }: { url: string }) {
  const href = safeUrl(url);
  if (!href) return <span className="mt-tech break-all">{url}</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="mt-tech break-all underline">
      {url}
    </a>
  );
}
