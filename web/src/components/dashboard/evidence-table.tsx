import { typeLabel } from "@/components/dashboard/labels";
import { Badge } from "@/components/ui/badge";

type EvidenceRow = {
  signature: string;
  evidence_snippet: string;
  finding_type: string;
  occurrences: number;
};

function preview(value: string): string {
  if (value.length <= 90) return value;
  return `${value.slice(0, 90)}…`;
}

function EvidenceTable({ rows }: { rows: EvidenceRow[] }) {
  return (
    <section className="mt-card flex min-w-0 flex-col gap-4 p-4" aria-labelledby="repeated-evidence-title">
      <h2 id="repeated-evidence-title" className="mt-section-title">
        Most repeated evidence
      </h2>
      {rows.length === 0 ? (
        <p className="mt-meta">No findings yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[28rem] border-collapse text-sm">
            <caption className="sr-only">Most repeated evidence snippets</caption>
            <thead>
              <tr className="text-left text-[11px] font-medium tracking-wide text-mt-faint uppercase">
                <th className="px-2 py-2 font-medium">Evidence</th>
                <th className="px-2 py-2 font-medium">Type</th>
                <th className="px-2 py-2 text-right font-medium">Occurrences</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((entry) => (
                <tr
                  key={entry.signature}
                  className="border-t border-mt-border transition-colors duration-150 hover:bg-mt-elevated motion-reduce:transition-none"
                >
                  <td className="max-w-[24rem] px-2 py-2">
                    <p className="mt-tech truncate" title={entry.evidence_snippet}>
                      {preview(entry.evidence_snippet)}
                    </p>
                  </td>
                  <td className="px-2 py-2">
                    <Badge variant="confidence">{typeLabel(entry.finding_type)}</Badge>
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums text-mt-fg">{entry.occurrences}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export { EvidenceTable };
