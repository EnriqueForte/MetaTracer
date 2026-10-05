import { Badge } from "@/components/ui/badge";
import { safeUrl } from "@/lib/security/safe-url";

import type { RunSnapshot } from "./run-model";

export function AssetIssues({ issues }: { issues: RunSnapshot["asset_issues"] }) {
  if (issues.length === 0) return null;
  return (
    <details className="rounded-md border border-mt-warning-border bg-mt-warning-bg p-3">
      <summary className="cursor-pointer text-sm text-mt-fg">
        Asset issues ({issues.length}) — failed or skipped documents that did not abort the run
      </summary>
      <ul className="mt-3 flex flex-col gap-2">
        {issues.map((issue) => {
          const href = safeUrl(issue.source_url);
          return (
            <li key={issue.asset_id} className="mt-tech">
              <Badge variant={issue.status === "failed" ? "failed" : "pending"}>
                {issue.skip_reason || issue.status}
              </Badge>{" "}
              {href ? (
                <a href={href} className="underline">
                  {issue.source_url}
                </a>
              ) : (
                issue.source_url
              )}
              {issue.error_message ? ` — ${issue.error_message}` : ""}
            </li>
          );
        })}
      </ul>
    </details>
  );
}
