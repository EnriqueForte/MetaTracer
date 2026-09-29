import { describe, expect, it } from "vitest";

import { installationHasAuthOff } from "@/lib/api/auth-mode";

describe("installationHasAuthOff", () => {
  it("hides register only when the installation reports auth off", () => {
    expect(installationHasAuthOff(200, { authenticated: false })).toBe(true);
    expect(installationHasAuthOff(401, { detail: "authentication required" })).toBe(false);
    expect(installationHasAuthOff(200, { authenticated: true, username: "a", role: "operator" })).toBe(false);
    expect(installationHasAuthOff(500, null)).toBe(false);
  });
});
