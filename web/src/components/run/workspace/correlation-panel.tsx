"use client";

import { useQuery } from "@tanstack/react-query";

import { errorMessage, getJson, isObject } from "@/lib/api/client";

type Member = {
  asset_id: string;
  asset_url: string;
  run_id: string;
  namespace: string;
  key: string;
};

type Group = {
  kind: string;
  value_norm: string;
  occurrences: number;
  notice: string;
  members: Member[];
  members_truncated: boolean;
};

type CorrelationList = {
  run_id: string;
  total: number;
  groups: Group[];
};

/** Shared values that touch this run. The notice is the server's sentence. */
export function CorrelationPanel({ runId }: { runId: string }) {
  const query = useQuery({
    queryKey: ["correlations", runId],
    queryFn: () =>
      getJson<CorrelationList>(
        `/api/runs/${encodeURIComponent(runId)}/correlations`,
        isCorrelationList,
      ),
  });

  if (query.isPending) return null;
  if (query.isError) {
    return (
      <p className="text-sm text-mt-danger" role="alert">
        {errorMessage(query.error, "No se pudieron cargar los valores compartidos")}
      </p>
    );
  }

  const groups = query.data?.groups ?? [];
  return (
    <section className="mt-card flex flex-col gap-2 p-4" aria-label="Valores compartidos">
      <h2 className="mt-section-title">Valores compartidos</h2>
      {groups.length === 0 ? (
        <p className="text-sm text-mt-muted">Ningún valor compartido enlaza este escaneo con otro activo.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {groups.map((group) => (
            <li key={`${group.kind}:${group.value_norm}`} className="flex flex-col gap-1">
              <p className="text-sm text-mt-fg">{group.notice}</p>
              <p className="mt-tech text-xs text-mt-muted">
                {group.kind} · {group.value_norm}
              </p>
              <ul className="flex flex-col gap-0.5">
                {group.members.map((member) => (
                  <li key={`${member.asset_id}:${member.namespace}:${member.key}`} className="mt-tech text-xs">
                    {member.namespace}:{member.key} · {member.asset_url}
                  </li>
                ))}
              </ul>
              {group.members_truncated ? (
                <p className="text-xs text-mt-muted">Algunos activos no aparecen en la lista.</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function isCorrelationList(value: unknown): value is CorrelationList {
  return isObject(value) && Array.isArray(value.groups);
}
