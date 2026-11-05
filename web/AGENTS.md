# MetaTracer Web UI — producto

Antes de tocar `web/`, lee la raíz:

- [`../AGENTS.md`](../AGENTS.md) — inviolables, un origen, render como texto
- [`../MEMORY.md`](../MEMORY.md) — specs abiertas; no implementar reserved
- Skill `metatracer-ui` — stack Next 16 / React 19 / Tailwind 4, `safeUrl`, CSP
- Dueño: subagente `v2-ui-engineer`. Contratos visuales: `ui-architect` (V2) y
  `.aicontext/ui/design-system-v2.md`. FastAPI es solo-API.

El bloque Next debajo lo reescribe `next dev`. **No borres este prefijo.**

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
