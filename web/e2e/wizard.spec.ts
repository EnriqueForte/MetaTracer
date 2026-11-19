import { expect, test, type Page } from "@playwright/test";

const SYNTH_RUN_ID = "e2e-graph-run";

const SYNTH_RUN = {
  run_id: SYNTH_RUN_ID,
  status: "running",
  target: "example.com",
  scope: ["example.com"],
  reasoning_depth: "standard",
  total_assets: 1,
  total_findings: 0,
  error_message: null,
  started_at: "2026-11-19T12:00:00Z",
  completed_at: null,
  asset_issues: [],
};

const SYNTH_GRAPH = {
  run_id: SYNTH_RUN_ID,
  crawl: {
    nodes: [
      {
        id: "page:https://example.com/",
        kind: "page",
        label: "https://example.com/",
        url: "https://example.com/",
        asset_id: null,
        correlation_kind: null,
        extraction_status: null,
      },
      {
        id: "asset:doc-1",
        kind: "asset",
        label: "https://example.com/report.pdf",
        url: "https://example.com/report.pdf",
        asset_id: "doc-1",
        correlation_kind: null,
        extraction_status: "ok",
      },
    ],
    edges: [{ from_id: "page:https://example.com/", to_id: "asset:doc-1", kind: "document" }],
    truncated: false,
    notice: null,
  },
  correlations: { nodes: [], edges: [], truncated: false, notice: null },
  metrics: {
    by_content_type: { "application/pdf": 1 },
    by_finding_type: {},
    by_extraction_status: { ok: 1 },
  },
};

async function stubSyntheticRun(page: Page): Promise<void> {
  await page.route("**/api/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/api/auth/me")) {
      await route.fulfill({ json: { authenticated: false } });
      return;
    }
    if (url.includes("/api/notifications")) {
      await route.fulfill({ json: { notifications: [] } });
      return;
    }
    if (url.includes(`/api/runs/${SYNTH_RUN_ID}/graph`)) {
      await route.fulfill({ json: SYNTH_GRAPH });
      return;
    }
    if (url.includes(`/api/runs/${SYNTH_RUN_ID}/stream`)) {
      await route.fulfill({
        status: 200,
        headers: { "content-type": "text/event-stream" },
        body: "retry: 15000\n\n",
      });
      return;
    }
    if (url.includes(`/api/runs/${SYNTH_RUN_ID}`)) {
      await route.fulfill({ json: SYNTH_RUN });
      return;
    }
    await route.fulfill({ status: 404, json: { detail: "not stubbed" } });
  });
}

test("the empty wizard does not mount a scan graph", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("region", { name: "Grafos del escaneo" })).toHaveCount(0);
});

test("a synthetic run page shows the scan graph region", async ({ page }) => {
  await stubSyntheticRun(page);
  await page.goto(`/runs/${SYNTH_RUN_ID}`);
  await expect(page.getByRole("region", { name: "Grafos del escaneo" })).toBeVisible();
  await expect(page.getByRole("img", { name: "Grafo de descubrimiento" })).toBeVisible();
});

test("scope modal stays closed until the checkbox is checked", async ({ page }) => {
  // T11: Web V2 serves from the origin root, so there is no /v2 prefix.
  await page.goto("/");
  await page.getByRole("button", { name: "Iniciar escaneo" }).click();
  await expect(page.getByText("Indica al menos un objetivo.")).toBeVisible();

  await page.getByLabel("Objetivos").fill("example.com");
  await page.getByLabel("Dominios de alcance autorizado").fill("example.com");
  await page.getByRole("button", { name: "Iniciar escaneo" }).click();

  await expect(page.getByRole("heading", { name: "Confirmar alcance autorizado" })).toBeVisible();
  await expect(page.getByRole("checkbox")).not.toBeChecked();
  await expect(page.getByRole("button", { name: "Confirmar e iniciar escaneo" })).toBeDisabled();
});
