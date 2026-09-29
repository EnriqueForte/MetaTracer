# Decisiones de arquitectura (ADRs)

ADRs breves: contexto, decisión, alternativas descartadas y consecuencias.
No duplican las tasks; las tasks dicen *qué* construir, estos archivos dicen *por qué*.

| ADR | Decisión |
| :--- | :--- |
| [0009](0009-same-finding-types-new-namespaces.md) | v1.2 amplía namespaces, no `finding_type` |
| [0010](0010-html-page-as-asset.md) | La página HTML del crawl es un `Asset` (sin segundo GET) |
| [0011](0011-http-header-allowlist.md) | Cabeceras HTTP: allowlist de recon, nunca cookies ni Authorization |

La numeración 0009–0011 sigue el número de task que cerró la decisión. No hay ADRs 0000–0008: las decisiones del MVP viven en las tasks y en [requisitos técnicos](../features/07-technical-requirements.md).

La serie `ADR-001` en `architecture/` es otra cosa: decisiones de plataforma que no cierran una task.

| ADR | Estado | Decisión |
| :--- | :--- | :--- |
| [ADR-001](../architecture/ADR-001-nextjs-react-migration.md) | Aceptada (2026-09-26) | Web V2 (Next.js) como cliente paralelo del FastAPI actual. No sustituye a la plataforma v2.0 ya construida ni a la UI Jinja. |
