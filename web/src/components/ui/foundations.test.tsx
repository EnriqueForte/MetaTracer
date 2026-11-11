import { cleanup, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";

afterEach(() => {
  cleanup();
});

describe("analytics foundations", () => {
  it("keeps the palette in CSS variables instead of a steel accent", () => {
    const css = readFileSync(path.join(process.cwd(), "src/app/globals.css"), "utf8");
    expect(css).toContain("--mt-bg: #06080c");
    expect(css).toContain("--mt-surface: #0c1118");
    expect(css).toContain("--mt-accent: #3cc4dc");
    expect(css).toContain("--mt-sev-critical: #ff6a76");
    expect(css).toContain("--mt-sev-high: #ff9a4a");
    expect(css).toContain("--mt-sev-low: #9ec5ff");
    expect(css).not.toContain("#6e8aa3");
  });

  it("renders a card, an empty state, an alert, and a loading status", () => {
    render(
      <Card>
        <EmptyState title="No scans yet">Run a scan to populate this view.</EmptyState>
      </Card>,
    );
    expect(screen.getByText("No scans yet")).toBeInTheDocument();
    cleanup();

    render(<ErrorState message="Could not load the dashboard data." />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load the dashboard data.");
    cleanup();

    render(<LoadingState label="Loading dashboard" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading dashboard");
  });
});
