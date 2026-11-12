"use client";

import { useQuery } from "@tanstack/react-query";

import { EmptyState, ErrorState } from "@/components/ui/states";
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

const KIND_LABEL: Record<string, string> = {
  email: "Correo",
  author_string: "Cadena de autor",
  gps_point: "Punto GPS",
  internal_endpoint: "Endpoint interno",
  software_version: "Versión de software",
  document_id: "Id de documento",
  device_serial: "Serie de dispositivo",
};

const TABLE_KINDS = new Set(["email", "author_string"]);

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

  if (query.isPending) {
    return <p className="text-sm text-mt-muted">Cargando valores compartidos…</p>;
  }
  if (query.isError) {
    return (
      <ErrorState
        message={errorMessage(query.error, "No se pudieron cargar los valores compartidos")}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const groups = query.data?.groups ?? [];
  const rollups = groups.filter((group) => TABLE_KINDS.has(group.kind));
  const others = groups.filter((group) => !TABLE_KINDS.has(group.kind));

  return (
    <section className="mt-card flex flex-col gap-3 p-4" aria-label="Valores compartidos">
      <h2 className="mt-section-title">Valores compartidos</h2>
      <p className="text-xs text-mt-muted">
        Un valor repetido no prueba identidad: es el mismo texto en más de un activo.
      </p>
      {groups.length === 0 ? (
        <EmptyState title="Ningún valor compartido">
          Ningún valor enlaza este escaneo con otro activo.
        </EmptyState>
      ) : null}
      {rollups.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="mt-table">
            <caption className="sr-only">Correos y cadenas de autor compartidos</caption>
            <thead>
              <tr>
                <th scope="col">Tipo</th>
                <th scope="col">Valor</th>
                <th scope="col" className="text-right">
                  Ocurrencias
                </th>
                <th scope="col">Activos</th>
              </tr>
            </thead>
            <tbody>
              {rollups.map((group) => (
                <tr key={`${group.kind}:${group.value_norm}`}>
                  <td>{KIND_LABEL[group.kind] ?? group.kind}</td>
                  <td className="mt-tech">{group.value_norm}</td>
                  <td className="text-right tabular-nums">{group.occurrences}</td>
                  <td className="mt-tech text-xs">
                    {group.members.map((member) => member.asset_url).join(" · ")}
                    {group.members_truncated ? " · …" : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {others.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {others.map((group) => (
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
      ) : null}
    </section>
  );
}

function isCorrelationList(value: unknown): value is CorrelationList {
  return isObject(value) && Array.isArray(value.groups);
}
