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

## Qué es histórico (no contrato)

- `.aicontext/ui/{design-system,ui-architecture,component-map,redesign-plan}.md`
- `.aicontext/architecture/phase-2.md` … `phase-15.md` y `phase-r1` … `phase-r6` (R1–R6 **hechos**)
- `.aicontext/migrations/` post-T11
- TASK-00–35: contratos de implementación **cerrados**; no mover a `archive/` el día uno (enlaces)

Contrato visual vigente: [`.aicontext/ui/design-system-v2.md`](../.aicontext/ui/design-system-v2.md).

## Fuera de este overlay

Watch `--cron` y el ejemplo systemd/compose están en spec 44 (closed). Deltas
“desaparecido / severity-up” siguen leftover en
[12-platform-v3.md](../.aicontext/features/12-platform-v3.md) (romperían `PAYLOAD_KEYS`).
