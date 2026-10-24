import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import net from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, it } from "node:test";

import { pythonExecutable, waitForPort } from "./dev-with-api.mjs";

describe("dev-with-api python lookup", () => {
  it("uses METATRACER_PYTHON when it is set", () => {
    assert.equal(
      pythonExecutable("/repo", "win32", { METATRACER_PYTHON: "C:\\py\\python.exe" }),
      "C:\\py\\python.exe",
    );
  });

  it("finds the Windows venv interpreter and falls back to system python", () => {
    const root = mkdtempSync(path.join(tmpdir(), "mt-dev-"));
    // No .venv -> the system interpreter (CI installs into the runner's Python).
    assert.equal(pythonExecutable(root, "win32", {}), "python");
    const bin = path.join(root, ".venv", "Scripts", "python.exe");
    mkdirSync(path.dirname(bin), { recursive: true });
    writeFileSync(bin, "");
    assert.equal(pythonExecutable(root, "win32", {}), bin);
  });

  it("falls back to python3 on POSIX when the venv is absent", () => {
    const root = mkdtempSync(path.join(tmpdir(), "mt-dev-"));
    assert.equal(pythonExecutable(root, "linux", {}), "python3");
  });

  it("finds the POSIX venv interpreter", () => {
    const root = mkdtempSync(path.join(tmpdir(), "mt-dev-"));
    const bin = path.join(root, ".venv", "bin", "python");
    mkdirSync(path.dirname(bin), { recursive: true });
    writeFileSync(bin, "");
    assert.equal(pythonExecutable(root, "linux", {}), bin);
  });

  it("resolves once a local port accepts connections", async () => {
    const server = net.createServer();
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    const { port } = server.address();
    await waitForPort(port, { timeoutMs: 2000, intervalMs: 20 });
    server.close();
  });
});
