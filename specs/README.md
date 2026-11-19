# Specs activas — MetaTracer

Overlay Spec-Driven Development. El corpus histórico vive en [`.aicontext/`](../.aicontext/PRD.md).
Este directorio es **solo trabajo abierto o reserved explícito**.

Memoria de sesión: [`MEMORY.md`](../MEMORY.md). Producto ahora: [`current.md`](current.md).
Backlog abierto: [`backlog.md`](backlog.md).

## Ritual SDD

1. Spec en `specs/NN-nombre.md` (`reserved` → `active`).
2. Enum nuevo: primero [`.aicontext/tasks/README.md`](../.aicontext/tasks/README.md) y
   `.cursor/rules/data-contracts.mdc`. La spec **enlaza**, no copia valores.
3. Task de implementación `.aicontext/tasks/NN-*.md` (mismo número).
4. Skill de módulo **al abrir** la slice, no antes (`.agents/skills.md`).
5. Código. Cierre: tick en `backlog.md` + una línea en `MEMORY.md`.

Un agente **no empieza código** si la spec está `reserved` o no hay task. Ver skill `metatracer-sdd`.

Estados: `reserved` \| `active` \| `closed`.

## Mapa

| Spec | Estado | Fuente `.aicontext` | Task | Skill | Agente |
| :--- | :--- | :--- | :--- | :--- | :--- |
| [00-sdd-governance](00-sdd-governance.md) | closed | — | overlay 2026-11-05 | `metatracer-sdd` | `docs-architect` |
| [36-investigations](36-investigations.md) | closed | `tasks/README.md` (Fase 3) | [TASK-36](../.aicontext/tasks/36-investigations.md) | `metatracer-investigations` | `pipeline-engineer` / `ui-engineer` |
| [37-new-detectors](37-new-detectors.md) | closed | contratos `finding_type` / `namespace` | [TASK-37](../.aicontext/tasks/37-new-detectors.md) | `detector-patterns` | `pipeline-engineer` |
| [38-connectors](38-connectors.md) | closed | `connector.status` Fase 4 | [TASK-38](../.aicontext/tasks/38-connectors.md) | `metatracer-platform` | `pipeline-engineer` + `ui-engineer` |
| [39-export-redaction](39-export-redaction.md) | closed | `export.redaction` Fase 5 | [TASK-39](../.aicontext/tasks/39-export-redaction.md) | `report-engine` | `pipeline-engineer` |
| [40-onnx-embeddings](40-onnx-embeddings.md) | closed | `features/12-platform-v3.md` Eje B | [TASK-40](../.aicontext/tasks/40-onnx-embeddings.md) | `metatracer-onnx` + supply-chain | `llm-agent-engineer` |
| [41-ops-hygiene](41-ops-hygiene.md) | closed | TASK-28/33 limitaciones | [TASK-41](../.aicontext/tasks/41-ops-hygiene.md) | `metatracer-platform` | `ui-engineer` / `pipeline-engineer` |
| [42-ui-operator](42-ui-operator.md) | closed | TASK-35 OOS, design-system-v2 | [TASK-42](../.aicontext/tasks/42-ui-operator.md) | `metatracer-ui` | `v2-ui-engineer` |
| [43-ui-investigations](43-ui-investigations.md) | closed | depende de 36 | [TASK-43](../.aicontext/tasks/43-ui-investigations.md) | `metatracer-ui` | `v2-ui-engineer` |
| [44-watch-cron](44-watch-cron.md) | closed | `features/12-platform-v3.md` Eje A | [TASK-44](../.aicontext/tasks/44-watch-cron.md) | `metatracer-platform` | `pipeline-engineer` |
| [45-ui-spanish](45-ui-spanish.md) | closed | contrato de idioma UI | [TASK-45](../.aicontext/tasks/45-ui-spanish.md) | `metatracer-ui` | `v2-ui-engineer` |
| [46-global-search](46-global-search.md) | closed | búsqueda global findings+metadata | [TASK-46](../.aicontext/tasks/46-global-search.md) | `metatracer-ui` | `ui-engineer` + `v2-ui-engineer` |
| [47-operator-workspace](47-operator-workspace.md) | closed | split pane, nav, rollups MIME/autor | [TASK-47](../.aicontext/tasks/47-operator-workspace.md) | `metatracer-ui` | `v2-ui-engineer` |
| [48-extraction-surface](48-extraction-surface.md) | closed | GIF/SVG, IPTC GPS, cloud URI, CSS url | [TASK-48](../.aicontext/tasks/48-extraction-surface.md) | `metadata-extraction` | `pipeline-engineer` |
| [49-secret-finding](49-secret-finding.md) | closed | `finding_type: secret` | [TASK-49](../.aicontext/tasks/49-secret-finding.md) | `detector-patterns` | `pipeline-engineer` |
| [50-watch-deltas](50-watch-deltas.md) | closed | desaparecido / severity-up + `PAYLOAD_KEYS` | [TASK-50](../.aicontext/tasks/50-watch-deltas.md) | `metatracer-platform` | `pipeline-engineer` |
| [51-local-ingest](51-local-ingest.md) | closed | carpeta local, cero red, mismos extractores | [TASK-51](../.aicontext/tasks/51-local-ingest.md) | `metadata-extraction` | `pipeline-engineer` |
| [52-ui-polish](52-ui-polish.md) | closed | pulido visual (jerarquía, cromo, login) | [TASK-52](../.aicontext/tasks/52-ui-polish.md) | `metatracer-ui` | `v2-ui-engineer` |
| [53-lab-target](53-lab-target.md) | closed | semanario lab Puertomontevideo | [TASK-53](../.aicontext/tasks/53-lab-target.md) | `metadata-extraction` + `detector-patterns` | lab (no `v2-ui-engineer`) |
| [54-lab-host](54-lab-host.md) | active | host HTTPS gratuito del lab | [TASK-54](../.aicontext/tasks/54-lab-host.md) | — | lab |
| [55-scan-live-graph](55-scan-live-graph.md) | closed | grafos en vivo del scan | [TASK-55](../.aicontext/tasks/55-scan-live-graph.md) | `metatracer-ui` | `pipeline-engineer` + `v2-ui-engineer` |
| [56-clone-install](56-clone-install.md) | closed | instalador + lanzador Windows/Linux | [TASK-56](../.aicontext/tasks/56-clone-install.md) | `metatracer-supply-chain` | `pipeline-engineer` |

## Qué es histórico (no contrato)

- `.aicontext/ui/{design-system,ui-architecture,component-map,redesign-plan}.md`
- `.aicontext/architecture/phase-2.md` … `phase-15.md` y `phase-r1` … `phase-r6` (R1–R6 **hechos**)
- `.aicontext/migrations/` post-T11
- TASK-00–35: contratos de implementación **cerrados**; no mover a `archive/` el día uno (enlaces)

Contrato visual vigente: [`.aicontext/ui/design-system-v2.md`](../.aicontext/ui/design-system-v2.md)
(tokens). Pulido: [`.aicontext/ui/polish-contract.md`](../.aicontext/ui/polish-contract.md).

## Fuera de este overlay

Watch `--cron` y el ejemplo systemd/compose están en spec 44 (closed). Deltas
“desaparecido / severity-up” están en [spec 50](50-watch-deltas.md) (closed;
`PAYLOAD_KEYS` incluye `resolved_findings` y `severity_up_count`). `secret`
está en el enum ([spec 49](49-secret-finding.md) closed). Ingesta local:
[spec 51](51-local-ingest.md) (closed). Pulido UI: [spec 52](52-ui-polish.md)
(closed; contrato en `.aicontext/ui/polish-contract.md`). Clone + instalador +
lanzador: [spec 56](56-clone-install.md) (closed).
