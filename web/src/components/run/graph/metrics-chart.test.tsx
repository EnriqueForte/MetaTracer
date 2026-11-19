import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { init, setOption } = vi.hoisted(() => {
  const setOption = vi.fn();
  const init = vi.fn(() => ({ setOption, dispose: vi.fn(), resize: vi.fn() }));
  return { init, setOption };
});

vi.mock("echarts/core", () => ({
  use: vi.fn(),
  init,
}));
vi.mock("echarts/charts", () => ({ BarChart: {} }));
vi.mock("echarts/components", () => ({ GridComponent: {}, TooltipComponent: {} }));
vi.mock("echarts/renderers", () => ({ CanvasRenderer: {} }));

import { MetricsChart } from "./metrics-chart";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("MetricsChart", () => {
  beforeEach(() => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: vi.fn().mockReturnValue({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }),
    });
  });

  it("renders empty copy without initializing echarts", () => {
    render(
      <MetricsChart
        metrics={{ by_content_type: {}, by_finding_type: {}, by_extraction_status: {} }}
      />,
    );
    expect(screen.getByText("Aún no hay métricas de inventario.")).toBeInTheDocument();
    expect(init).not.toHaveBeenCalled();
  });

  it("initializes canvas charts with richText tooltips", () => {
    render(
      <MetricsChart
        metrics={{
          by_content_type: { "application/pdf": 2 },
          by_finding_type: { email: 1 },
          by_extraction_status: { ok: 2 },
        }}
      />,
    );
    expect(screen.getByRole("img", { name: "Por tipo MIME" })).toBeInTheDocument();
    expect(init).toHaveBeenCalled();
    const option = setOption.mock.calls[0]?.[0] as
      | { tooltip?: { renderMode: string }; series?: Array<{ type: string }> }
      | undefined;
    expect(option?.tooltip?.renderMode).toBe("richText");
    expect(option?.series?.[0]?.type).toBe("bar");
  });
});
