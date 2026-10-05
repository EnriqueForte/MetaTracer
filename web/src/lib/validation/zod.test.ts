import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { z } from "@/lib/validation/zod";

const SRC = path.resolve(__dirname, "../..");

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return name === "generated" ? [] : sources(full);
    return /\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [full] : [];
  });
}

describe("Zod under the production CSP", () => {
  it("runs jitless so it never probes new Function", () => {
    expect(z.config().jitless).toBe(true);
  });

  it("is only imported through the jitless wrapper", () => {
    const wrapper = path.join(SRC, "lib", "validation", "zod.ts");
    const offenders = sources(SRC).filter(
      (file) => file !== wrapper && /from\s+["']zod(\/[^"']*)?["']/.test(readFileSync(file, "utf8")),
    );
    expect(offenders).toEqual([]);
  });
});
