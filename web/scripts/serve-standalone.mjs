/**
 * Boots the Next standalone server for the Playwright webServers.
 *
 * `output: 'standalone'` (needed by the Docker image) emits a self-contained
 * server but deliberately leaves `public/` and `.next/static` out: the deploy
 * step is expected to copy them next to server.js. `next start` refuses to run
 * entirely under standalone, so the e2e cannot use it.
 *
 * This mirrors what web/Dockerfile does at image-build time.
 */
import { cpSync, existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const standaloneCandidates = [
  path.join(root, ".next", "standalone"),
  path.join(root, ".next", "standalone", "web"),
];
const standalone = standaloneCandidates.find((dir) => existsSync(path.join(dir, "server.js")));

if (!standalone) {
  console.error("web/.next/standalone/server.js missing. Run `npm run build` first.");
  process.exit(1);
}

const publicSrc = path.join(root, "public");
const publicDst = path.join(standalone, "public");
if (existsSync(publicSrc)) {
  mkdirSync(publicDst, { recursive: true });
  cpSync(publicSrc, publicDst, { recursive: true });
}

const staticSrc = path.join(root, ".next", "static");
const staticDst = path.join(standalone, ".next", "static");
if (existsSync(staticSrc)) {
  mkdirSync(staticDst, { recursive: true });
  cpSync(staticSrc, staticDst, { recursive: true });
}

process.chdir(standalone);
// PathToFileURL is required on Windows: a bare "C:\..." is not a valid ESM specifier.
const { pathToFileURL } = await import("node:url");
await import(pathToFileURL(path.join(standalone, "server.js")).href);
