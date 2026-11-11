"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "@/lib/validation/zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { errorMessage, getJson, sendJson } from "@/lib/api/client";
import { queryKeys } from "@/lib/query/keys";
import { useActor } from "@/lib/session";
import { formatWhen } from "@/lib/time";

type Webhook = {
  id: string;
  name: string | null;
  url: string;
  event: "completed" | "failed" | "aborted";
  headers: Record<string, string>;
  max_retries: number;
  active: boolean;
  signature_status: "active" | "needs_secret" | "none";
  created_at: string;
};

type Delivery = {
  id: string;
  run_id: string;
  status: string;
  attempts: number;
  max_retries: number;
  status_code: number | null;
  last_error: string | null;
  created_at: string;
};

const EVENTS = ["completed", "failed", "aborted"] as const;

const SIGNATURE_LABEL: Record<Webhook["signature_status"], string> = {
  active: "Firmado (HMAC)",
  needs_secret: "Vuelve a introducir el secreto",
  none: "Sin firmar",
};

const EVENT_LABEL: Record<(typeof EVENTS)[number], string> = {
  completed: "Completado",
  failed: "Fallido",
  aborted: "Abortado",
};

const webhookSchema = z.object({
  name: z.string().trim().max(80, "Los nombres tienen como máximo 80 caracteres."),
  url: z
    .string()
    .trim()
    .url("Indica una URL completa.")
    .refine((value) => value.toLowerCase().startsWith("https://"), "Las URL de webhook deben usar HTTPS."),
  event: z.enum(EVENTS),
  max_retries: z.number().int().min(0, "Al menos 0 reintentos.").max(10, "Como máximo 10 reintentos."),
  signature_secret: z.string().max(256, "Los secretos tienen como máximo 256 caracteres."),
  headers: z.record(z.string(), z.string()),
});

/** `Name: value` per line. Values are sent once and never displayed back. */
export function parseHeaderLines(text: string): Record<string, string> | string {
  const headers: Record<string, string> = {};
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const at = line.indexOf(":");
    if (at <= 0) return `Las cabeceras van como "Nombre: valor" (se recibió "${line.slice(0, 40)}").`;
    const name = line.slice(0, at).trim();
    if (!/^[A-Za-z0-9-]+$/.test(name)) return `Los nombres de cabecera usan letras, dígitos y guiones (se recibió "${name.slice(0, 40)}").`;
    headers[name] = line.slice(at + 1).trim();
  }
  return headers;
}

function isWebhookList(value: unknown): boolean {
  return Array.isArray(value);
}

function Deliveries({ webhookId }: { webhookId: string }) {
  const query = useQuery({
    queryKey: [...queryKeys.webhooks, webhookId, "deliveries"],
    queryFn: () => getJson<Delivery[]>(`/api/webhooks/${encodeURIComponent(webhookId)}/deliveries`, isWebhookList),
  });
  if (query.isPending) return <p className="text-xs text-mt-muted">Cargando entregas…</p>;
  if (query.isError) return <p className="text-xs text-mt-danger">{errorMessage(query.error, "No se pudieron cargar las entregas")}</p>;
  if (query.data.length === 0) return <p className="text-xs text-mt-muted">Aún no hay entregas.</p>;
  return (
    <table className="w-full text-xs">
      <caption className="sr-only">Entregas</caption>
      <thead>
        <tr className="text-left text-mt-muted">
          <th className="py-1 font-medium">Estado</th>
          <th className="py-1 font-medium">Intentos</th>
          <th className="py-1 font-medium">HTTP</th>
          <th className="py-1 font-medium">Creado (UTC)</th>
          <th className="py-1 font-medium">Último error</th>
        </tr>
      </thead>
      <tbody>
        {query.data.map((row) => (
          <tr key={row.id} className="border-t border-mt-border">
            <td className="py-1">{row.status}</td>
            <td className="py-1 tabular-nums">
              {row.attempts}/{row.max_retries}
            </td>
            <td className="py-1 tabular-nums">{row.status_code ?? "—"}</td>
            <td className="mt-tech py-1">{formatWhen(row.created_at)}</td>
            <td className="mt-tech py-1">{row.last_error ?? ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function WebhooksView() {
  const actor = useActor();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [event, setEvent] = useState<(typeof EVENTS)[number]>("completed");
  const [retries, setRetries] = useState(3);
  const [secret, setSecret] = useState("");
  const [headersText, setHeadersText] = useState("");
  const [formError, setFormError] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [rotate, setRotate] = useState<Record<string, string>>({});

  const list = useQuery({
    queryKey: queryKeys.webhooks,
    queryFn: () => getJson<Webhook[]>("/api/webhooks", isWebhookList),
    enabled: actor === "operator",
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.webhooks });

  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => sendJson("/api/webhooks", "POST", body),
    onSuccess: () => {
      setName("");
      setUrl("");
      setSecret("");
      setHeadersText("");
      setRetries(3);
      void refresh();
    },
    onError: (error) => setFormError(errorMessage(error, "No se pudo crear el webhook")),
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      sendJson(`/api/webhooks/${encodeURIComponent(id)}`, "PUT", body),
    onSuccess: (_data, variables) => {
      setRotate((current) => ({ ...current, [variables.id]: "" }));
      void refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => sendJson(`/api/webhooks/${encodeURIComponent(id)}`, "DELETE"),
    onSuccess: () => void refresh(),
  });

  if (actor === "viewer") {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="mt-title">Webhooks</h1>
        <p role="alert" className="text-sm text-mt-warning">Se requiere el rol de operador</p>
      </div>
    );
  }

  function submit() {
    setFormError("");
    const headers = parseHeaderLines(headersText);
    if (typeof headers === "string") {
      setFormError(headers);
      return;
    }
    const parsed = webhookSchema.safeParse({ name, url, event, max_retries: retries, signature_secret: secret, headers });
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Revisa el formulario.");
      return;
    }
    const { signature_secret, name: label, ...rest } = parsed.data;
    create.mutate({
      ...rest,
      name: label || null,
      signature_secret: signature_secret || null,
      active: true,
    });
  }

  const rows = list.data ?? [];
  const actionError = update.error ?? remove.error;

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div>
        <h1 className="mt-title">Webhooks</h1>
        <p className="text-sm text-mt-fg">
          Notificaciones de salida cuando termina un escaneo. Solo HTTPS. Los valores de cabecera y el
          secreto de firma son de solo escritura: no se vuelven a mostrar después de guardar.
        </p>
      </div>
      <section className="flex flex-col gap-3 rounded-md border border-mt-border bg-mt-surface p-4" aria-label="Nuevo webhook">
        <h2 className="text-sm font-semibold">Nuevo webhook</h2>
        <form className="grid grid-cols-1 gap-3 md:grid-cols-2" noValidate onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <div className="flex flex-col gap-1">
            <label htmlFor="hook-name" className="text-xs font-semibold text-mt-muted">Nombre (opcional)</label>
            <Input id="hook-name" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="hook-url" className="text-xs font-semibold text-mt-muted">URL HTTPS</label>
            <Input id="hook-url" className="mt-tech" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://hooks.example.com/metatracer" />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="hook-event" className="text-xs font-semibold text-mt-muted">Evento</label>
            <select id="hook-event" value={event} onChange={(e) => { const next = EVENTS.find((item) => item === e.target.value); if (next) setEvent(next); }} className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm">
              {EVENTS.map((item) => <option key={item} value={item}>{EVENT_LABEL[item]}</option>)}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="hook-retries" className="text-xs font-semibold text-mt-muted">Reintentos máximos</label>
            <Input id="hook-retries" type="number" min={0} max={10} value={retries} onChange={(e) => setRetries(Number(e.target.value))} />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="hook-secret" className="text-xs font-semibold text-mt-muted">Secreto de firma (opcional)</label>
            <Input id="hook-secret" type="password" autoComplete="off" value={secret} onChange={(e) => setSecret(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="hook-headers" className="text-xs font-semibold text-mt-muted">Cabeceras extra (opcional, una &quot;Nombre: valor&quot; por línea)</label>
            <textarea id="hook-headers" rows={2} value={headersText} onChange={(e) => setHeadersText(e.target.value)} className="mt-tech rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm" />
          </div>
          {formError ? <p role="alert" className="text-sm text-mt-danger md:col-span-2">{formError}</p> : null}
          <div className="md:col-span-2">
            <Button type="submit" disabled={create.isPending}>Crear webhook</Button>
          </div>
        </form>
      </section>
      {actionError ? <p role="alert" className="text-sm text-mt-danger">{errorMessage(actionError, "No se pudo actualizar el webhook")}</p> : null}
      {list.isError ? <ErrorState message={errorMessage(list.error, "No se pudieron cargar los webhooks")} onRetry={() => void list.refetch()} /> : null}
      {list.isSuccess && rows.length === 0 ? <EmptyState title="Aún no hay webhooks">Crea uno para recibir aviso cuando termine un escaneo.</EmptyState> : null}
      {rows.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {rows.map((hook) => (
            <li key={hook.id} className="mt-card flex flex-col gap-2 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-mt-fg">{hook.name || "Webhook sin nombre"}</p>
                  <p className="mt-tech">{hook.url}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={hook.active ? "completed" : "pending"}>{hook.active ? "Activo" : "En pausa"}</Badge>
                  <Badge variant="confidence">en {EVENT_LABEL[hook.event]}</Badge>
                  <Badge variant={hook.signature_status === "needs_secret" ? "aborted" : "confidence"}>
                    {SIGNATURE_LABEL[hook.signature_status]}
                  </Badge>
                </div>
              </div>
              {Object.keys(hook.headers).length > 0 ? (
                <p className="text-xs text-mt-muted">Cabeceras: {Object.keys(hook.headers).join(", ")} (valores ocultos)</p>
              ) : null}
              <div className="flex flex-wrap items-end gap-2">
                <Button variant="secondary" className="px-2 py-1 text-xs" onClick={() => update.mutate({ id: hook.id, body: { active: !hook.active } })}>
                  {hook.active ? "Pausar" : "Reanudar"}
                </Button>
                <div className="flex items-end gap-2">
                  <div className="flex flex-col gap-1">
                    <label htmlFor={`rotate-${hook.id}`} className="text-xs text-mt-muted">Nuevo secreto de firma</label>
                    <Input id={`rotate-${hook.id}`} type="password" autoComplete="off" value={rotate[hook.id] ?? ""} onChange={(e) => setRotate((current) => ({ ...current, [hook.id]: e.target.value }))} />
                  </div>
                  <Button
                    variant="secondary"
                    className="px-2 py-1 text-xs"
                    disabled={!(rotate[hook.id] ?? "").trim()}
                    onClick={() => update.mutate({ id: hook.id, body: { signature_secret: (rotate[hook.id] ?? "").trim() } })}
                  >
                    Guardar secreto
                  </Button>
                </div>
                <Button variant="ghost" className="px-2 py-1 text-xs" aria-expanded={open === hook.id} onClick={() => setOpen((current) => (current === hook.id ? null : hook.id))}>
                  {open === hook.id ? "Ocultar entregas" : "Mostrar entregas"}
                </Button>
                <Button
                  variant="danger"
                  className="px-2 py-1 text-xs"
                  onClick={() => {
                    if (window.confirm("¿Eliminar este webhook? También se borra su historial de entregas.")) remove.mutate(hook.id);
                  }}
                >
                  Eliminar
                </Button>
              </div>
              {open === hook.id ? <Deliveries webhookId={hook.id} /> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
