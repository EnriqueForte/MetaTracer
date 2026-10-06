import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(webRoot, "..");

/** Venv interpreter for `metatracer serve`. Never falls back to a system Python. */
export function pythonExecutable(root, platform = process.platform, env = process.env) {
  const override = env.METATRACER_PYTHON;
  if (typeof override === "string" && override.trim()) return override.trim();
  const candidate =
    platform === "win32"
      ? path.join(root, ".venv", "Scripts", "python.exe")
      : path.join(root, ".venv", "bin", "python");
  return existsSync(candidate) ? candidate : null;
}

/** Resolves when something accepts TCP connections. Retries until timeout. */
export function waitForPort(port, { host = "127.0.0.1", timeoutMs = 30_000, intervalMs = 200, signal } = {}) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const attempt = () => {
      if (signal?.aborted) {
        reject(new Error("stopped"));
        return;
      }
      const socket = net.connect({ host, port });
      const finish = (ok) => {
        socket.removeAllListeners();
        socket.destroy();
        if (ok) {
          resolve();
          return;
        }
        if (Date.now() - started >= timeoutMs) {
          reject(new Error(`API did not listen on ${host}:${port}`));
          return;
        }
        setTimeout(attempt, intervalMs);
      };
      socket.once("connect", () => finish(true));
      socket.once("error", () => finish(false));
    };
    attempt();
  });
}

async function start() {
  const python = pythonExecutable(repoRoot);
  if (!python) {
    process.stderr.write(
      "No virtualenv Python found. From the repo root run:\n" +
        "  python -m venv .venv\n" +
        "  .venv\\Scripts\\python.exe -m pip install -e \".[dev]\"\n",
    );
    process.exit(1);
  }

  const nextBin = path.join(webRoot, "node_modules", "next", "dist", "bin", "next");
  process.stdout.write(
    "MetaTracer\n  API  http://127.0.0.1:8000\n  App  http://127.0.0.1:3000/v2\n",
  );

  const children = [
    spawn(python, ["-m", "metatracer", "serve"], {
      cwd: repoRoot,
      stdio: "inherit",
    }),
  ];

  let stopping = false;
  function stop(code) {
    if (stopping) return;
    stopping = true;
    for (const child of children) {
      if (child.exitCode === null && child.signalCode === null) child.kill();
    }
    const finish = () => process.exit(code);
    if (children.every((child) => child.exitCode !== null || child.signalCode !== null)) finish();
    else {
      for (const child of children) child.once("exit", () => {
        if (children.every((item) => item.exitCode !== null || item.signalCode !== null)) finish();
      });
    }
  }

  function watch(child) {
    child.on("exit", (code) => {
      if (!stopping) stop(code ?? 1);
    });
  }
  watch(children[0]);
  process.on("SIGINT", () => stop(130));
  process.on("SIGTERM", () => stop(143));

  const abort = new AbortController();
  children[0].once("exit", () => abort.abort());
  try {
    await waitForPort(8000, { signal: abort.signal });
  } catch (error) {
    if (!stopping) {
      process.stderr.write(`${error instanceof Error ? error.message : "API did not start"}\n`);
      stop(1);
    }
    return;
  }
  if (stopping) return;
  const web = spawn(process.execPath, [nextBin, "dev"], {
    cwd: webRoot,
    stdio: "inherit",
  });
  children.push(web);
  watch(web);
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) start();
