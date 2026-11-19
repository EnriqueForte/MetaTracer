# MEMORY — MetaTracer

Memoria de trabajo para agentes. No es un PRD. Si un hecho no cabe aquí, vive en
`specs/`, `.aicontext/` o el código.

**Última actualización:** 2026-11-19 (spec 55 closed: grafos en vivo del scan)

## Estado del producto

- Versión: **v3.2 cerrada** (2026-10-05). Suite rechecked 2026-10-23: 787 passed, 6 skipped, cobertura 91.30%.
- UI: **Web V2** (Next.js 16 + React 19 + Tailwind 4) en `web/`, servida desde la **raíz del origen**. FastAPI es solo-API. Web V1 (Jinja + Alpine) retirada (ADR-0016).
- Trabajo **activo** (gobernanza): [`specs/`](specs/README.md). Backlog de producto: [`specs/backlog.md`](specs/backlog.md). One-pager: [`specs/current.md`](specs/current.md).
- TASK-00 → TASK-35 y TASK-36–53 están **cerradas**. Spec **54 active**: host público del lab (no producto). Spec **55 closed**: grafos en vivo del scan.

## Dónde está la verdad

| Cosa | Fuente |
| :--- | :--- |
| Enums y contratos | `.aicontext/tasks/README.md` **y** `.cursor/rules/data-contracts.mdc` |
| Safety inviolable | `.cursor/rules/safety-invariants.mdc` |
| Spec activa / reserved | `specs/` |
| Contrato de implementación | `.aicontext/tasks/NN-*.md` (solo cuando la spec pasa a `active`) |
| Contrato visual vigente | `.aicontext/ui/design-system-v2.md` |
| Catálogo de agentes | `.agents/agents.md` |
| Skills cargables | `.cursor/skills/<name>/SKILL.md` (índice: `.agents/skills.md`) |

Las specs **no duplican** enums: enlazan.

## Prohibición (specs reserved)

Spec 54 **active** (host público del lab). Spec 55 **closed** (grafos en vivo del scan). Specs 36–53 **closed**. No hay reserved.

## Specs

| Spec | Estado |
| :--- | :--- |
| [00-sdd-governance](specs/00-sdd-governance.md) | closed |
| [36-investigations](specs/36-investigations.md) | closed |
| [37-new-detectors](specs/37-new-detectors.md) | closed |
| [38-connectors](specs/38-connectors.md) | closed |
| [39-export-redaction](specs/39-export-redaction.md) | closed |
| [40-onnx-embeddings](specs/40-onnx-embeddings.md) | closed |
| [41-ops-hygiene](specs/41-ops-hygiene.md) | closed |
| [42-ui-operator](specs/42-ui-operator.md) | closed |
| [43-ui-investigations](specs/43-ui-investigations.md) | closed |
| [44-watch-cron](specs/44-watch-cron.md) | closed |
| [45-ui-spanish](specs/45-ui-spanish.md) | closed |
| [46-global-search](specs/46-global-search.md) | closed |
| [47-operator-workspace](specs/47-operator-workspace.md) | closed |
| [48-extraction-surface](specs/48-extraction-surface.md) | closed |
| [49-secret-finding](specs/49-secret-finding.md) | closed |
| [50-watch-deltas](specs/50-watch-deltas.md) | closed |
| [51-local-ingest](specs/51-local-ingest.md) | closed |
| [52-ui-polish](specs/52-ui-polish.md) | closed |
| [53-lab-target](specs/53-lab-target.md) | closed |
| [54-lab-host](specs/54-lab-host.md) | active |
| [55-scan-live-graph](specs/55-scan-live-graph.md) | closed |

## Docs stale (no reintroducir como contrato)

- `.aicontext/PRD.md` índice aún habla de dashboard “en v2.0” — el dashboard existe.
- `.aicontext/ui/{design-system,ui-architecture,component-map,redesign-plan}.md` y `architecture/phase-*` = **histórico V1**.
- `architecture/ADR-001-nextjs-react-migration.md` habla de coexistencia; manda ADR-0016 (cutover).
- `web/AGENTS.md` lo reescribe `next dev`; el prefijo de producto debe quedar **encima** del bloque Next.

## Safety (postura vigente)

Las 7 reglas de `safety-invariants.mdc`. Loopback bloqueado salvo `METATRACER_ALLOW_LOOPBACK=true` en tests. Auth cookie + CSRF en API; CLI sin login. Un solo origen, `connect-src 'self'`.

## Ritual al cerrar una slice

1. Marcar la spec `closed` y tildar [`specs/backlog.md`](specs/backlog.md).
2. Una línea en esta sección **Cierre reciente**.
3. Si hubo enum nuevo: ya está en `tasks/README.md` + rule (no al revés).

### Cierre reciente

- 2026-11-05 — overlay SDD: `MEMORY.md`, `specs/`, skills `metatracer-sdd` y `metatracer-platform`, catálogos alineados. Sin código de producto.
- 2026-11-05 — TASK-36: CLI `metatracer investigation`; spec 36 closed. Backend/API de investigations ya existían.
- 2026-11-05 — TASK-43: `/investigations` listado y ficha; nav Research; palette. Sugerencias de triage sin auto-aplicar.
- 2026-11-05 — TASK-37: `internal_endpoint` y `cloud_storage` emitidos; OOXML/ODF propiedades-only. Código ya en el árbol; enums desbloqueados.
- 2026-11-05 — TASK-39: `export.redaction` en el fichero exportado; API/CLI default `none`; UI propone `contacts`. BD intacta.
- 2026-11-05 — TASK-38: conectores RDAP/Wayback/CC; `connector.status`; apagado no abre socket; 429 = `degraded`.
- 2026-11-05 — TASK-41: lock durable de scans, `resume` de aborted, `GET /api/metrics`, alias `/api/v1`.
- 2026-11-05 — TASK-40: MiniLM ONNX local 384-d (extra `[onnx]`); fallback hashing-trick; sin descarga.
- 2026-11-05 — TASK-42: triage masivo API/CLI/UI; densidad en findings; atajo `x`.
- 2026-11-05 — TASK-44: `watch --cron` UTC 5 campos (stdlib); unit systemd; compose profile `watch`.
- 2026-11-11 — TASK-45: Web UI en español; reportes exportados y CLI siguen en inglés.
- 2026-11-12 — Overlay v3.4: specs 46–51 **reserved** (búsqueda global, workspace operador, extracción GIF/SVG/GPS/cloud URI, `secret`, watch deltas, ingest local). Sin código de producto.
- 2026-11-12 — TASK-46: `GET /api/search`, CLI `search`, UI `/search` y paleta de evidencia. Spec 46 closed.
- 2026-11-12 — TASK-47: split pane de hallazgos, `[`/`]`, Comparar en nav, Integraciones en paleta, MIME/autor rollups, LayerChip, estados compartidos. Spec 47 closed.
- 2026-11-12 — TASK-48: GIF/SVG metadata-only, GPS IPTC, `s3://`/`gs://`/Spaces/Wasabi, `url()` CSS in-scope. Spec 48 closed. HEIC/AVIF OOS.
- 2026-11-13 — TASK-49: `finding_type: secret` (AKIA / `ghp_` / PEM / JWT compact en metadata extraída). Spec 49 closed. Bodies/JS/TruffleHog OOS.
- 2026-11-13 — TASK-50: watch `resolved_findings` / `severity_up_count` en webhook (escalares). Spec 50 closed.
- 2026-11-13 — TASK-51: ingesta local (`--local` / `local_paths`), cero red, mismos sniff/extractores. Spec 51 closed. Unpack ZIP OOS.
- 2026-11-13 — spec 52 reserved: contrato de pulido UI (`.aicontext/ui/polish-contract.md`). Sin código.
- 2026-11-13 — TASK-52: pulido Web V2 (jerarquía, cromo de run, wizard sin Recorrido, login estático). Spec 52 closed.
- 2026-11-14 — TASK-53: lab `puertomontevideo` (fotos Commons, actas inventadas, toponimia de Montevideo, preview local). Spec 53 closed. Deploy público y scan loopback OOS.
- 2026-11-19 — TASK-55: grafo de crawl y de correlación en la ficha del run (`GET /api/runs/{id}/graph`, ECharts + Cytoscape empaquetados). Spec 55 closed. Mapas, OSINT de identidad y CLI con grafo OOS.
