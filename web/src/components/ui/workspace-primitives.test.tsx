import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DensitySwitch } from "@/components/ui/density-switch";
import { RawValue } from "@/components/ui/raw-value";
import { SplitPane } from "@/components/ui/split-pane";
import { LayerChip, StatusChip } from "@/components/ui/status-chip";

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute("data-density");
  window.localStorage.clear();
});

describe("SplitPane", () => {
  it("keeps the list mounted when the panel opens (no modal, no lost state)", () => {
    const { rerender } = render(
      <SplitPane panel={null} panelLabel="Detail">
        <p>row one</p>
      </SplitPane>,
    );
    expect(screen.getByText("row one")).toBeInTheDocument();
    expect(screen.queryByRole("separator")).toBeNull();

    rerender(
      <SplitPane panel={<p>detail</p>} panelLabel="Detail">
        <p>row one</p>
      </SplitPane>,
    );
    expect(screen.getByText("row one")).toBeInTheDocument();
    expect(screen.getByText("detail")).toBeInTheDocument();
    expect(screen.getByRole("separator", { name: "Redimensionar el panel de detalle" })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Detail" })).toBeInTheDocument();
  });

  it("resizes with the keyboard and clamps to the bounds", () => {
    render(
      <SplitPane panel={<p>detail</p>} panelLabel="Detail" min={320} max={720} defaultWidth={420}>
        <p>row</p>
      </SplitPane>,
    );
    const handle = screen.getByRole("separator");
    expect(handle).toHaveAttribute("aria-valuenow", "420");

    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(handle).toHaveAttribute("aria-valuenow", "436");

    fireEvent.keyDown(handle, { key: "Home" });
    expect(handle).toHaveAttribute("aria-valuenow", "720");

    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(handle).toHaveAttribute("aria-valuenow", "720"); // clamped at max

    fireEvent.keyDown(handle, { key: "End" });
    expect(handle).toHaveAttribute("aria-valuenow", "320");
  });

  it("ignores a corrupted stored width instead of breaking the layout", () => {
    window.localStorage.setItem("mt-panel-width", "not-a-number");
    render(
      <SplitPane panel={<p>detail</p>} panelLabel="Detail" defaultWidth={400}>
        <p>row</p>
      </SplitPane>,
    );
    expect(screen.getByRole("separator")).toHaveAttribute("aria-valuenow", "400");
  });
});

describe("DensitySwitch", () => {
  beforeEach(() => {
    document.documentElement.removeAttribute("data-density");
  });

  it("defaults to comfortable and writes the attribute for CSS", () => {
    render(<DensitySwitch />);
    expect(screen.getByRole("radio", { name: "Cómoda" })).toHaveAttribute("aria-checked", "true");
    expect(document.documentElement.getAttribute("data-density")).toBe("comfortable");
  });

  it("persists the compact choice", () => {
    render(<DensitySwitch />);
    fireEvent.click(screen.getByRole("radio", { name: "Compacta" }));
    expect(document.documentElement.getAttribute("data-density")).toBe("compact");
    expect(window.localStorage.getItem("mt-density")).toBe("compact");
    expect(screen.getByRole("radio", { name: "Compacta" })).toHaveAttribute("aria-checked", "true");
  });
});

describe("RawValue", () => {
  it("shows the stored value and flags truncation", () => {
    render(<RawValue value="Adobe InDesign[truncated]" truncated />);
    expect(screen.getByText("Adobe InDesign[truncated]")).toBeInTheDocument();
    expect(screen.getByText("Truncado")).toBeInTheDocument();
  });

  it("renders as text, never as markup", () => {
    const { container } = render(<RawValue value="<img src=x onerror=alert(1)>" />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
  });

  it("collapses long values and expands them on demand", () => {
    const long = "x".repeat(400);
    render(<RawValue value={long} />);
    const button = screen.getByRole("button", { name: "Mostrar valor completo" });
    expect(button).toBeInTheDocument();
    fireEvent.click(button);
    expect(screen.getByRole("button", { name: "Mostrar menos" })).toBeInTheDocument();
  });

  it("shows the normalized form beside the original when present", () => {
    render(<RawValue value='["40/1", "24/1", "4635/100"]' normalized="40.410097" />);
    expect(screen.getByText('["40/1", "24/1", "4635/100"]')).toBeInTheDocument();
    expect(screen.getByText("Normalizado")).toBeInTheDocument();
    expect(screen.getByText("40.410097")).toBeInTheDocument();
  });
});

describe("Provenance", () => {
  it("labels every layer with text, not only colour", () => {
    render(
      <>
        <LayerChip layer="observed" />
        <LayerChip layer="inferred" />
        <LayerChip layer="external" />
      </>,
    );
    expect(screen.getByText("Observado")).toBeInTheDocument();
    expect(screen.getByText("Inferido")).toBeInTheDocument();
    expect(screen.getByText("Externo")).toBeInTheDocument();
  });

  it("keeps the extraction status readable as a word", () => {
    render(<StatusChip tone="skipped" label="Skipped" />);
    expect(screen.getByText("Skipped")).toBeInTheDocument();
  });
});

describe("SplitPane persistence", () => {
  it("restores a valid stored width", () => {
    window.localStorage.setItem("mt-panel-width", "512");
    render(
      <SplitPane panel={<p>detail</p>} panelLabel="Detail" min={320} max={720}>
        <p>row</p>
      </SplitPane>,
    );
    expect(screen.getByRole("separator")).toHaveAttribute("aria-valuenow", "512");
  });

  it("clamps a stored width above the maximum", () => {
    window.localStorage.setItem("mt-panel-width", "99999");
    render(
      <SplitPane panel={<p>detail</p>} panelLabel="Detail" min={320} max={720}>
        <p>row</p>
      </SplitPane>,
    );
    expect(screen.getByRole("separator")).toHaveAttribute("aria-valuenow", "720");
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});
