import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Button } from "@/components/ui/button";

afterEach(cleanup);

describe("Button toggle variant", () => {
  it("styles the pressed state, not only announces it", () => {
    render(
      <>
        <Button variant="toggle" aria-pressed>
          On
        </Button>
        <Button variant="toggle" aria-pressed={false}>
          Off
        </Button>
      </>,
    );
    const on = screen.getByRole("button", { name: "On" });
    expect(on).toHaveAttribute("aria-pressed", "true");
    expect(on.className).toContain("aria-pressed:border-mt-accent");
    expect(on.className).toContain("aria-pressed:text-mt-accent-hover");
    expect(screen.getByRole("button", { name: "Off" })).toHaveAttribute("aria-pressed", "false");
  });
});
