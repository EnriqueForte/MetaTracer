# Spec 52 — Pulido visual Web V2

**Estado:** closed  
**Agente previsto:** `v2-ui-engineer` · contrato: `ui-architect` (ya emitido)  
**Skill al abrir:** `metatracer-ui`  
**Task:** [.aicontext/tasks/52-ui-polish.md](../.aicontext/tasks/52-ui-polish.md)

## Intención

El overlay v3.4 (specs 36–51) cubre el producto. Esta slice **no añade
capacidad**: aplica el [contrato de pulido](../.aicontext/ui/polish-contract.md)
para que el operador vea más claro y tarde menos. Paleta `--mt-*` intacta.
Movimiento solo al cambiar de estado.

## Alcance (cerrado)

Cabezas `.mt-page-head`, una CTA `primary` por vista, wizard sin “Recorrido”
decorativo, un cromo de run (hallazgos solo en `/findings`), tabs de una línea,
login sin rejilla ni keyframes, `EmptyState`/`LoadingState` compactos. Copy UI
en español.

## Fuera de alcance

Nueva paleta. Animaciones de adorno. Unpack ZIP, Wayback, HEIC. Producto nuevo.
Dependencias nuevas.

## Dependencias

[`design-system-v2.md`](../.aicontext/ui/design-system-v2.md) +
[`polish-contract.md`](../.aicontext/ui/polish-contract.md). Specs 42/45/47 closed.
