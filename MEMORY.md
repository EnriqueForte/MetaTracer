# MEMORY — MetaTracer

Memoria de trabajo para agentes. No es un PRD. Si un hecho no cabe aquí, vive en
`specs/`, `.aicontext/` o el código.

**Última actualización:** 2026-11-11 (TASK-45 closed: Web UI en español)

## Estado del producto

- Versión: **v3.2 cerrada** (2026-10-05). Suite rechecked 2026-10-23: 787 passed, 6 skipped, cobertura 91.30%.
- UI: **Web V2** (Next.js 16 + React 19 + Tailwind 4) en `web/`, servida desde la **raíz del origen**. FastAPI es solo-API. Web V1 (Jinja + Alpine) retirada (ADR-0016).
- Trabajo **activo** (gobernanza): [`specs/`](specs/README.md). Backlog de producto: [`specs/backlog.md`](specs/backlog.md). One-pager: [`specs/current.md`](specs/current.md).
- TASK-00 → TASK-35 y TASK-36–44 están **cerradas**.

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

No hay specs reserved. Deltas watch “desaparecido / severity-up” siguen leftover en `.aicontext/features/12-platform-v3.md` (sin spec; romperían `PAYLOAD_KEYS`).

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
