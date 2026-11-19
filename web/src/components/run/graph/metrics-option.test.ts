import { describe, expect, it } from "vitest";

import { hasMetricData, metricSeries } from "./metrics-option";

describe("metricSeries", () => {
  it("drops empty maps and labels finding types in Spanish", () => {
    const series = metricSeries({
      by_content_type: { "application/pdf": 3 },
      by_finding_type: { email: 2 },
      by_extraction_status: {},
    });
    expect(series).toHaveLength(2);
    expect(series[0]?.labels).toEqual(["application/pdf"]);
    expect(series[1]?.labels).toEqual(["Correo"]);
    expect(hasMetricData({ by_content_type: {}, by_finding_type: {}, by_extraction_status: {} })).toBe(
      false,
    );
  });
});
