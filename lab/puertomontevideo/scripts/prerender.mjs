import { build } from "esbuild";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");
const outfile = join(dist, ".ssr.mjs");

await mkdir(dist, { recursive: true });

await build({
  absWorkingDir: root,
  entryPoints: ["src/ssr.tsx"],
  bundle: true,
  format: "esm",
  platform: "node",
  outfile,
  jsx: "automatic",
  packages: "external",
});

const { pages } = await import(pathToFileURL(outfile).href);
const required = ["/media/grua4.jpg", "/media/acta-terminal.pdf", "/app.js"];
const home = pages["index.html"] ?? "";
for (const href of required.slice(0, 2)) {
  if (!home.includes(href)) {
    throw new Error(`prerender home is missing ${href}`);
  }
}
const template = await readFile(join(root, "index.html"), "utf8");

for (const [name, markup] of Object.entries(pages)) {
  const html = template
    .replace('<div id="root"></div>', `<div id="root">${markup}</div>`)
    .replace(
      '<script type="module" src="/src/main.tsx"></script>',
      "",
    );
  if (name === "index.html" && !html.includes("/app.js")) {
    throw new Error("prerendered index.html is missing /app.js");
  }
  await writeFile(join(dist, name), html, "utf8");
  console.log(`prerendered ${name}`);
}
