import { describe, expect, it } from "vitest";

import { safeUrl } from "@/lib/security/safe-url";

describe("safeUrl", () => {
  it("accepts http and https", () => {
    expect(safeUrl("https://example.com/a.jpg")).toBe("https://example.com/a.jpg");
    expect(safeUrl("http://example.com/a")).toBe("http://example.com/a");
  });

  it("rejects javascript, data, and empty values", () => {
    expect(safeUrl("javascript:alert(1)")).toBeNull();
    expect(safeUrl("data:text/html,<script>alert(1)</script>")).toBeNull();
    expect(safeUrl("")).toBeNull();
    expect(safeUrl("not a url")).toBeNull();
  });
});
