import { describe, expect, it } from "vitest";

import { installationHasAuthOff, setupIsAvailable } from "@/lib/api/auth-mode";

describe("installationHasAuthOff", () => {
  it("hides register only when the installation reports auth off", () => {
    expect(installationHasAuthOff(200, { authenticated: false })).toBe(true);
    expect(installationHasAuthOff(401, { detail: "authentication required" })).toBe(false);
    expect(installationHasAuthOff(200, { authenticated: true, username: "a", role: "operator" })).toBe(false);
    expect(installationHasAuthOff(500, null)).toBe(false);
  });
});

describe("setupIsAvailable (T9)", () => {
  it("is true only when the API reports an open setup flow", () => {
    expect(setupIsAvailable({ setup_available: true })).toBe(true);
    expect(setupIsAvailable({ authenticated: true, setup_available: false })).toBe(false);
    expect(setupIsAvailable({ detail: "authentication required" })).toBe(false);
    expect(setupIsAvailable(null)).toBe(false);
    expect(setupIsAvailable("setup_available")).toBe(false);
  });
});
