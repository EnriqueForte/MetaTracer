# Fase 4 — tokens y primitivas

**Fecha:** 2026-09-29
**Estado:** Cerrada. Sin páginas de dominio. `src/metatracer/` no cambió.

## Decisión de Tailwind

Web V2 usa **Tailwind CSS 4.3.3** (`@tailwindcss/postcss` 4.3.3), solo como herramienta de build en `web/`. Web V1 sigue con Tailwind 3.4.16 compilado en `/static`. Los tokens no dependen de la versión mayor: son las mismas variables `--mt-*` de `metatracer.css`.

## Lista añadida (pins exactos)

Runtime: `lucide-react@1.48.0`, `clsx@2.1.1`, `tailwind-merge@3.7.0`, `class-variance-authority@0.7.1`, `@radix-ui/react-slot@1.3.3`, `@radix-ui/react-dialog@1.1.23`.

Dev: `tailwindcss@4.3.3`, `@tailwindcss/postcss@4.3.3`.

Sin CLI de shadcn, sin CDN, sin fuentes remotas, sin TanStack Query ni Zod. Los componentes están copiados en `web/src/components/ui/`: `button`, `input`, `badge`, `table`, `dialog`, `sheet`.

El badge cubre la escala de severidad y los estados de run ya definidos (`critical`…`info`, `unclassified`, `pending`, `running`, `completed`, `failed`, `aborted`). No calcula severidad.

`dialog` y `sheet` no usan desenfoque de fondo. El overlay es `--mt-overlay`. No hay `dangerouslySetInnerHTML`.

La tipografía de evidencia (`.mt-evidence`, `.mt-tech`, `.mt-title`) vive en `web/src/app/globals.css`.

La página `/v2` sigue siendo la fundación: fondo `#0c1014`, título y una línea en el color secundario. No hay wizard ni tabla de hallazgos.
