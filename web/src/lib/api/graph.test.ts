import { describe, expect, it } from "vitest";

import { correlationKindsIn, filterCorrelationLayer, isRunGraph } from "@/lib/api/graph";

const valid = {
  run_id: "run-1",
  crawl: { nodes: [], edges: [], truncated: false, notice: null },
  correlations: { nodes: [], edges: [], truncated: false, notice: null },
  metrics: { by_content_type: {}, by_finding_type: {}, by_extraction_status: {} },
};

describe("isRunGraph", () => {
  it("accepts the empty live payload", () => {
    expect(isRunGraph(valid)).toBe(true);
  });

  it("rejects a node without a closed kind", () => {
    expect(
      isRunGraph({
        ...valid,
        crawl: {
          nodes: [{ id: "n", kind: "identity", label: "x", url: null, asset_id: null, correlation_kind: null, extraction_status: null }],
          edges: [],
          truncated: false,
          notice: null,
        },
      }),
    ).toBe(false);
  });
});

describe("filterCorrelationLayer", () => {
  const layer = {
    nodes: [
      {
        id: "value:mail",
        kind: "value" as const,
        label: "ada@example.com",
        url: null,
        asset_id: null,
        correlation_kind: "email",
        extraction_status: null,
      },
      {
        id: "value:ver",
        kind: "value" as const,
        label: "wordpress 6.4.2",
        url: null,
        asset_id: null,
        correlation_kind: "software_version",
        extraction_status: null,
      },
      {
        id: "asset:a",
        kind: "asset" as const,
        label: "https://example.com/a.pdf",
        url: "https://example.com/a.pdf",
        asset_id: "a",
        correlation_kind: null,
        extraction_status: "ok",
      },
      {
        id: "asset:b",
        kind: "asset" as const,
        label: "https://example.com/b.pdf",
        url: "https://example.com/b.pdf",
        asset_id: "b",
        correlation_kind: null,
        extraction_status: "ok",
      },
    ],
    edges: [
      { from_id: "asset:a", to_id: "value:mail", kind: "email" },
      { from_id: "asset:b", to_id: "value:ver", kind: "software_version" },
    ],
    truncated: false,
    notice: null,
  };

  it("lists kinds in contract order", () => {
    expect(correlationKindsIn(layer)).toEqual(["email", "software_version"]);
  });

  it("keeps only the selected value and its assets", () => {
    const filtered = filterCorrelationLayer(layer, "email");
    expect(filtered.nodes.map((node) => node.id)).toEqual(["value:mail", "asset:a"]);
    expect(filtered.edges).toEqual([{ from_id: "asset:a", to_id: "value:mail", kind: "email" }]);
  });
});
