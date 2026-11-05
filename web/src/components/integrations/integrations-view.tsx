"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { errorMessage, getJson, isObject, sendJson } from "@/lib/api/client";

type ConnectorCard = {
  id: string;
  label: string;
  kind: string;
  enabled: boolean;
  status: "disabled" | "available" | "degraded" | "error";
  sends: string[];
  egress_hosts: string[];
  notice: string;
};

type Lookup = {
  domain: string;
  status: string;
  detail: string | null;
  registrar: string | null;
  statuses: string[];
  nameservers: string[];
  events: string[][];
  provenance: { connector_id: string; source_url: string; retrieved_at: string };
};

export function IntegrationsView() {
  const queryClient = useQueryClient();
  const [domain, setDomain] = useState("");
  const [waybackDomain, setWaybackDomain] = useState("");
  const [crawlDomain, setCrawlDomain] = useState("");
  const [lookup, setLookup] = useState<Lookup | null>(null);
  const [wayback, setWayback] = useState<{
    status: string;
    detail: string | null;
    replay_fetched: boolean;
    captures: { capture_date: string; original_url: string }[];
  } | null>(null);
  const [formError, setFormError] = useState("");
  const list = useQuery({
    queryKey: ["connectors"],
    queryFn: () =>
      getJson<{ connectors: ConnectorCard[] }>("/api/connectors", (value) => {
        return isObject(value) && Array.isArray(value.connectors);
      }),
  });

  const toggle = useMutation({
    mutationFn: (enabled: boolean) => sendJson<ConnectorCard>("/api/connectors/rdap", "PUT", { enabled }),
    onSuccess: () => {
      setFormError("");
      void queryClient.invalidateQueries({ queryKey: ["connectors"] });
    },
    onError: (error) => setFormError(errorMessage(error, "Could not update the connector.")),
  });

  const testLookup = useMutation({
    mutationFn: (name: string) => sendJson<Lookup>("/api/connectors/rdap/lookup", "POST", { domain: name }),
    onSuccess: (row) => {
      setFormError("");
      setLookup(row);
    },
    onError: (error) => setFormError(errorMessage(error, "The lookup did not complete.")),
  });

  const card = list.data?.connectors.find((item) => item.id === "rdap");
  const waybackCard = list.data?.connectors.find((item) => item.id === "wayback");
  const crawlCard = list.data?.connectors.find((item) => item.id === "commoncrawl");
  const waybackToggle = useMutation({
    mutationFn: (enabled: boolean) =>
      sendJson<ConnectorCard>("/api/connectors/wayback", "PUT", { enabled }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["connectors"] }),
    onError: (error) => setFormError(errorMessage(error, "Could not update Wayback.")),
  });
  const waybackSearch = useMutation({
    mutationFn: (name: string) =>
      sendJson<{
        status: string;
        detail: string | null;
        replay_fetched: boolean;
        captures: { capture_date: string; original_url: string }[];
      }>("/api/connectors/wayback/search", "POST", { domain: name }),
    onSuccess: (row) => {
      setFormError("");
      setWayback(row);
    },
    onError: (error) => setFormError(errorMessage(error, "The CDX search did not complete.")),
  });
  const crawlToggle = useMutation({
    mutationFn: (enabled: boolean) =>
      sendJson<ConnectorCard>("/api/connectors/commoncrawl", "PUT", { enabled }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["connectors"] }),
    onError: (error) => setFormError(errorMessage(error, "Could not update Common Crawl.")),
  });
  const crawlSearch = useMutation({
    mutationFn: (name: string) =>
      sendJson("/api/connectors/commoncrawl/search", "POST", { domain: name }),
    onSuccess: () => setFormError(""),
    onError: (error) => setFormError(errorMessage(error, "The index search did not complete.")),
  });

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div>
        <h1 className="mt-title">Integrations</h1>
        <p className="text-sm text-mt-muted">
          Connectors send data to a provider. They are off until an operator enables them, and they
          do not widen a scan scope.
        </p>
      </div>
      {list.isError ? (
        <p className="text-sm text-mt-danger" role="alert">
          {errorMessage(list.error, "Could not load connectors")}
        </p>
      ) : null}
      {card ? (
        <section className="mt-card flex flex-col gap-3 p-4" aria-label="RDAP">
          <h2 className="mt-section-title">RDAP</h2>
          <p className="text-sm text-mt-fg">{card.notice}</p>
          <p className="text-xs text-mt-muted">
            Sends: {card.sends.join(", ")}. Bootstrap host: {card.egress_hosts.join(", ")}. Status:{" "}
            {card.enabled ? "enabled" : "disabled"}.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              disabled={toggle.isPending}
              onClick={() => toggle.mutate(!card.enabled)}
            >
              {card.enabled ? "Disable RDAP" : "Enable RDAP"}
            </Button>
          </div>
          <form
            className="flex flex-wrap items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              const name = domain.trim();
              if (!name) {
                setFormError("Enter a domain name.");
                return;
              }
              testLookup.mutate(name);
            }}
          >
            <label htmlFor="rdap-domain" className="text-xs font-semibold text-mt-muted">
              Domain
            </label>
            <input
              id="rdap-domain"
              value={domain}
              onChange={(event) => setDomain(event.target.value)}
              placeholder="example.com"
              className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg"
            />
            <Button type="submit" variant="secondary" disabled={testLookup.isPending || !card.enabled}>
              Test connection
            </Button>
          </form>
          {lookup ? (
            <div className="text-sm text-mt-fg">
              <p>
                {lookup.domain}: {lookup.status}
                {lookup.detail ? ` — ${lookup.detail}` : ""}
              </p>
              {lookup.registrar ? <p>Registrar: {lookup.registrar}</p> : null}
              <p className="mt-tech text-xs text-mt-muted">Source: {lookup.provenance.source_url}</p>
            </div>
          ) : null}
          {formError ? (
            <p className="text-sm text-mt-danger" role="alert">
              {formError}
            </p>
          ) : null}
        </section>
      ) : null}
      {waybackCard ? (
        <section className="mt-card flex flex-col gap-3 p-4" aria-label="Wayback CDX">
          <h2 className="mt-section-title">Wayback CDX</h2>
          <p className="text-sm text-mt-fg">{waybackCard.notice}</p>
          <p className="text-xs text-mt-muted">
            Status: {waybackCard.enabled ? "enabled" : "disabled"}. Archived pages are not downloaded.
          </p>
          <Button
            variant="secondary"
            disabled={waybackToggle.isPending}
            onClick={() => waybackToggle.mutate(!waybackCard.enabled)}
          >
            {waybackCard.enabled ? "Disable Wayback" : "Enable Wayback"}
          </Button>
          <form
            className="flex flex-wrap items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              const name = waybackDomain.trim();
              if (!name) {
                setFormError("Enter a domain name.");
                return;
              }
              waybackSearch.mutate(name);
            }}
          >
            <label htmlFor="wayback-domain" className="text-xs font-semibold text-mt-muted">
              Domain
            </label>
            <input
              id="wayback-domain"
              value={waybackDomain}
              onChange={(event) => setWaybackDomain(event.target.value)}
              placeholder="example.com"
              className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg"
            />
            <Button
              type="submit"
              variant="secondary"
              disabled={waybackSearch.isPending || !waybackCard.enabled}
            >
              Search captures
            </Button>
          </form>
          {wayback ? (
            <div className="text-sm text-mt-fg">
              <p>
                {wayback.status}
                {wayback.detail ? ` — ${wayback.detail}` : ""}. Replay fetched:{" "}
                {wayback.replay_fetched ? "yes" : "no"}.
              </p>
              <ul>
                {wayback.captures.map((item) => (
                  <li key={`${item.capture_date}:${item.original_url}`} className="mt-tech text-xs">
                    {item.capture_date} · {item.original_url}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}
      {crawlCard ? (
        <section className="mt-card flex flex-col gap-3 p-4" aria-label="Common Crawl">
          <h2 className="mt-section-title">Common Crawl</h2>
          <p className="text-sm text-mt-fg">{crawlCard.notice}</p>
          <p className="text-xs text-mt-muted">
            Status: {crawlCard.enabled ? "enabled" : "disabled"}. WARC files are not downloaded.
          </p>
          <Button
            variant="secondary"
            disabled={crawlToggle.isPending}
            onClick={() => crawlToggle.mutate(!crawlCard.enabled)}
          >
            {crawlCard.enabled ? "Disable Common Crawl" : "Enable Common Crawl"}
          </Button>
          <form
            className="flex flex-wrap items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              const name = crawlDomain.trim();
              if (!name) {
                setFormError("Enter a domain name.");
                return;
              }
              crawlSearch.mutate(name);
            }}
          >
            <label htmlFor="crawl-domain" className="text-xs font-semibold text-mt-muted">
              Domain
            </label>
            <input
              id="crawl-domain"
              value={crawlDomain}
              onChange={(event) => setCrawlDomain(event.target.value)}
              placeholder="example.com"
              className="rounded-md border border-mt-border-strong bg-mt-bg px-3 py-2 text-sm text-mt-fg"
            />
            <Button type="submit" variant="secondary" disabled={crawlSearch.isPending || !crawlCard.enabled}>
              Search index
            </Button>
          </form>
        </section>
      ) : null}
    </div>
  );
}
