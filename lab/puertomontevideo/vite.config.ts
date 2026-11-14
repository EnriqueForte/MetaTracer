import { defineConfig, type PreviewServer, type ViteDevServer } from "vite";
import react from "@vitejs/plugin-react";

const LAB_PAGES = new Set([
  "/acta.html",
  "/fotogaleria.html",
  "/redaccion.html",
  "/descargas.html",
]);

const RECON_HEADERS: Record<string, string> = {
  Server: "Microsoft-IIS/10.0",
  "X-Powered-By": "ASP.NET",
  "X-AspNet-Version": "4.0.30319",
  "X-Backend-Server": "cms.puertomontevideo.internal",
  "X-Debug": "staging-token-lab-only",
  "X-Generator": "WordPress 6.4.2",
};

function applyReconHeaders(server: ViteDevServer | PreviewServer) {
  server.middlewares.use((_req, res, next) => {
    for (const [name, value] of Object.entries(RECON_HEADERS)) {
      res.setHeader(name, value);
    }
    next();
  });
}

function spaFallback(server: ViteDevServer) {
  server.middlewares.use((req, _res, next) => {
    const url = req.url?.split("?")[0] ?? "";
    if (LAB_PAGES.has(url)) {
      req.url = "/index.html";
    }
    next();
  });
}

export default defineConfig({
  plugins: [
    react(),
    {
      name: "lab-recon-and-pages",
      configureServer(server) {
        applyReconHeaders(server);
        spaFallback(server);
      },
      configurePreviewServer: applyReconHeaders,
    },
  ],
  build: {
    manifest: true,
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
  },
});
