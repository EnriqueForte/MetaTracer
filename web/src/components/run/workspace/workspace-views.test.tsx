import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders as render } from "@/test/render";

import { AssetsView } from "@/components/run/workspace/assets-view";
import { CoverageView } from "@/components/run/workspace/coverage-view";
import { MetadataExplorer } from "@/components/run/workspace/metadata-explorer";
import { WorkspaceProvider } from "@/components/run/workspace/workspace-context";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/runs/run-1/metadata");
  window.localStorage.clear();
});

const run = {
  run_id: "run-1",
  status: "completed",
  target: "acme.test",
  scope: ["acme.test"],
  reasoning_depth: "standard",
  total_assets: 3,
  total_findings: 1,
  error_message: null,
  started_at: "2026-10-01T10:00:00Z",
  completed_at: "2026-10-01T10:05:00Z",
  asset_issues: [],
};

const assets = {
  run_id: "run-1",
  total: 3,
  has_more: false,
  next_cursor: null,
  assets: [
    {
      id: "a1",
      source_url: "https://acme.test/report.pdf",
      final_url: "https://acme.test/report.pdf",
      content_type: "application/pdf",
      file_hash_sha256: "aa".repeat(32),
      file_size_bytes: 2048,
      extraction_status: "ok",
      skip_reason: null,
      error_message: null,
      discovered_at: "2026-10-01T10:00:00Z",
      metadata_fields: 3,
      findings: 1,
    },
    {
      id: "a2",
      source_url: "https://acme.test/photo.jpg",
      final_url: "https://acme.test/photo.jpg",
      content_type: "image/jpeg",
      file_hash_sha256: "bb".repeat(32),
      file_size_bytes: 4096,
      extraction_status: "ok",
      skip_reason: null,
      error_message: null,
      discovered_at: "2026-10-01T10:00:01Z",
      metadata_fields: 2,
      findings: 0,
    },
    {
      id: "a3",
      source_url: "https://acme.test/blob.bin",
      final_url: "https://acme.test/blob.bin",
      content_type: "application/octet-stream",
      file_hash_sha256: "cc".repeat(32),
      file_size_bytes: 0,
      extraction_status: "skipped",
      skip_reason: "unsupported_type",
      error_message: "magic bytes match no supported type",
      discovered_at: "2026-10-01T10:00:02Z",
      metadata_fields: 0,
      findings: 0,
    },
  ],
};

const metadata = {
  run_id: "run-1",
  total: 2,
  has_more: false,
  next_cursor: null,
  items: [
    {
      id: 1,
      asset_id: "a1",
      asset_url: "https://acme.test/report.pdf",
      namespace: "pdfinfo",
      key: "Author",
      value: "jane@acme.test",
      truncated: false,
    },
    {
      id: 2,
      asset_id: "a2",
      asset_url: "https://acme.test/photo.jpg",
      namespace: "exif",
      key: "GPSLatitude",
      value: '["40/1", "24/1", "4635/100"]',
      truncated: false,
      value_normalized: "40.412875",
      normalized_kind: "decimal_degrees",
      timezone_status: null,
    },
  ],
};

const coverage = {
  run_id: "run-1",
  status: "completed",
  total_assets: 3,
  ok: 2,
  skipped: 1,
  failed: 0,
  bytes_downloaded: 6144,
  metadata_fields: 5,
  findings: 1,
  by_skip_reason: { unsupported_type: 1 },
  by_namespace: { pdfinfo: 3, exif: 2 },
  counters_recorded: false,
  limits_hit: [],
  budget: {},
  pages_crawled: 0,
  assets_queued: 0,
  elapsed_seconds: 0,
};

function stubFetch(overrides: Record<string, unknown> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/auth/me")) {
        return new Response(JSON.stringify({ authenticated: false }), { status: 200 });
      }
      if (url.includes("/correlations")) {
        return new Response(
          JSON.stringify(
            overrides.correlations ?? { run_id: "run-1", total: 0, groups: [] },
          ),
          { status: 200 },
        );
      }
      if (url.includes("/coverage")) {
        return new Response(JSON.stringify(overrides.coverage ?? coverage), { status: 200 });
      }
      if (url.includes("/metadata")) {
        return new Response(JSON.stringify(overrides.metadata ?? metadata), { status: 200 });
      }
      if (url.includes("/assets")) {
        return new Response(JSON.stringify(overrides.assets ?? assets), { status: 200 });
      }
      return new Response(JSON.stringify(run), { status: 200 });
    }),
  );
}

function wrap(view: React.ReactNode) {
  return (
    <WorkspaceProvider runId="run-1">
      {view}
    </WorkspaceProvider>
  );
}

describe("AssetsView", () => {
  it("lists every asset, including the successful ones", async () => {
    stubFetch();
    render(wrap(<AssetsView />));
    const table = await screen.findByRole("table", { name: "Assets discovered in this run" });
    expect(within(table).getAllByRole("row")).toHaveLength(4); // header + 3
    expect(within(table).getAllByText("Extracted").length).toBeGreaterThan(0);
    expect(within(table).queryByText("Duplicate content")).toBeNull();
  });

  it("opens a persistent detail pane with the asset metadata", async () => {
    stubFetch();
    render(wrap(<AssetsView />));
    const row = await screen.findByText("https://acme.test/report.pdf");
    fireEvent.click(row);
    const panel = await screen.findByRole("complementary", { name: "Asset detail" });
    expect(within(panel).getByText("application/pdf")).toBeInTheDocument();
    expect(within(panel).getByText("2.0 KB")).toBeInTheDocument();
  });

  it("shows an empty state that does not claim nothing exists", async () => {
    stubFetch({ assets: { ...assets, total: 0, assets: [] } });
    render(wrap(<AssetsView />));
    expect(await screen.findByText("No assets")).toBeInTheDocument();
    expect(
      screen.getByText("This run did not record any asset with the current filter."),
    ).toBeInTheDocument();
  });
});

describe("MetadataExplorer", () => {
  it("states that a shared value is not a shared identity", async () => {
    stubFetch({
      correlations: {
        run_id: "run-1",
        total: 1,
        groups: [
          {
            kind: "device_serial",
            value_norm: "sn-88421",
            occurrences: 2,
            first_seen_run_id: "run-1",
            notice: "Shared value across 2 assets — not proof of common identity.",
            members_truncated: false,
            members: [
              {
                asset_id: "a1",
                asset_url: "https://acme.test/photo.jpg",
                run_id: "run-1",
                namespace: "exif",
                key: "BodySerialNumber",
              },
            ],
          },
        ],
      },
    });
    render(wrap(<MetadataExplorer />));
    expect(
      await screen.findByText("Shared value across 2 assets — not proof of common identity."),
    ).toBeInTheDocument();
    expect(screen.getByText(/device_serial/)).toBeInTheDocument();
  });

  it("renders stored fields that produce no finding", async () => {
    stubFetch();
    render(wrap(<MetadataExplorer />));
    const table = await screen.findByRole("table", {
      name: "Metadata fields stored for this run",
    });
    expect(within(table).getByText("Author")).toBeInTheDocument();
    expect(within(table).getByText("GPSLatitude")).toBeInTheDocument();
    expect(within(table).getByText("40.412875")).toBeInTheDocument();
  });

  it("opens the value detail with provenance and the original value", async () => {
    stubFetch();
    render(wrap(<MetadataExplorer />));
    fireEvent.click(await screen.findByText("Author"));
    const panel = await screen.findByRole("complementary", { name: "Field detail" });
    expect(within(panel).getByText("Observed")).toBeInTheDocument();
    expect(within(panel).getByText("jane@acme.test")).toBeInTheDocument();
    expect(within(panel).getByText("pdfinfo")).toBeInTheDocument();
  });

  it("writes the search into the URL so a view is shareable", async () => {
    stubFetch();
    render(wrap(<MetadataExplorer />));
    const search = await screen.findByLabelText(/Search metadata by value or field name/i);
    fireEvent.change(search, { target: { value: "canon" } });
    expect(window.location.search).toContain("q=canon");
  });

  it("shows the namespace facet counts from coverage", async () => {
    stubFetch();
    render(wrap(<MetadataExplorer />));
    expect(await screen.findByRole("button", { name: "pdfinfo (3)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "exif (2)" })).toBeInTheDocument();
  });
});

describe("CoverageView", () => {
  it("reports what was stored and refuses to invent discovery counters", async () => {
    stubFetch();
    render(wrap(<CoverageView />));
    expect(await screen.findByText("Coverage of this run")).toBeInTheDocument();
    expect(screen.getByText("Assets recorded")).toBeInTheDocument();
    expect(screen.getByText("Unsupported type")).toBeInTheDocument();
    // The honesty requirement: not-recorded must not read as zero.
    expect(screen.getByText(/Discovery counters are/i)).toBeInTheDocument();
    expect(screen.getByText(/The number of resources discovered but not attempted is unknown, not zero/i)).toBeInTheDocument();
    expect(screen.queryByText(/0 resources/i)).not.toBeInTheDocument();
  });

  it("lists the limits reached and the applied budget when counters are recorded", async () => {
    stubFetch({
      coverage: {
        ...coverage,
        counters_recorded: true,
        limits_hit: ["max_assets"],
        budget: {
          depth: 1,
          max_pages: 1,
          max_assets: 3,
          max_total_bytes: 1000000,
          max_seconds: 60,
          max_concurrency: 2,
        },
        pages_crawled: 1,
        assets_queued: 2,
        elapsed_seconds: 1.5,
      },
    });
    render(wrap(<CoverageView />));
    expect(await screen.findByText(/Asset limit was reached/i)).toBeInTheDocument();
    expect(screen.queryByText(/Discovery counters are/i)).not.toBeInTheDocument();
    // The applied budget is shown, so the analyst sees the ceiling that applied.
    expect(screen.getByText("Crawl depth")).toBeInTheDocument();
    expect(screen.getByText("2/3")).toBeInTheDocument(); // assets queued / max
  });

  it("says a robots.txt omission is courtesy and not authorization", async () => {
    stubFetch({
      coverage: {
        ...coverage,
        counters_recorded: true,
        limits_hit: [],
        budget: {
          depth: 1,
          max_pages: 1,
          max_assets: 3,
          max_total_bytes: 1000000,
          max_seconds: 60,
          max_concurrency: 2,
        },
        robots_checked: true,
        robots_omitted: 2,
        sitemaps_ignored: 1,
        sitemaps_truncated: true,
      },
    });
    render(wrap(<CoverageView />));
    expect(await screen.findByText(/robots.txt was consulted/i)).toBeInTheDocument();
    expect(screen.getByText(/That is courtesy/i)).toBeInTheDocument();
    expect(screen.getByText(/never widens/i)).toBeInTheDocument();
    expect(screen.getByText(/stopped at its cap/i)).toBeInTheDocument();
  });
});
