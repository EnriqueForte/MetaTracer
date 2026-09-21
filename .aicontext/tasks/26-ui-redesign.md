# TASK-26 — Rediseño de UI: design system propio sobre el stack actual

**Fuente:** decisión de producto 2026-09-19 (prioridad del operador: "diseño mucho mejor" para la Web UI).
**Estado:** **rediseño visual aplicado 2026-09-21** sobre el stack actual (Jinja2 + Alpine.js 3.14.8 + Tailwind 3.4.16 por CDN fijado). Contrato en [`.aicontext/ui/`](../ui/redesign-plan.md). La retirada del CDN (opciones A/B de abajo) y las cabeceras HTTP de seguridad siguen como seguimiento; no forman parte de este cierre. La base a11y de TASK-20 se revalidó (`pytest` 675 passed, 5 skipped, ruff limpio; revisión de `safety-guardian` sin bloqueantes).
**Dependencias:** TASK-00 … TASK-25 (en particular TASK-20, cuya base a11y se conserva).

## Objetivo

Elevar la Web UI de "funcional y accesible" a un producto con identidad visual propia, manteniendo el stack (Jinja2 + Alpine.js) y sin romper los contratos de TASK-20 (matriz de estados, `MetaTracerUI`, focus/ARIA/teclado, inglés de UI).

## Decisiones de diseño

- **Stack se mantiene** (Jinja2 + Alpine.js + Tailwind): no hay framework SPA ni build de Node en el repo. El rediseño es de design system y layout, no de arquitectura.
- **Tailwind compilado, CDN fuera** (deuda anotada desde TASK-20): el CDN de `cdn.tailwindcss.com` emite un warning de producción, influye en el FCP y añade un tercero en cada page-load. Sustituir por una hoja compilada servida desde `/static`:
  - Opción A (preferida): **Tailwind standalone CLI** (binario oficial pinned por SHA, sin Node/npm en el repo) que compila `static/app.css` desde las clases usadas; el binario vive fuera de la lista de dependencias Python y su revisión supply-chain se documenta aquí.
  - Opción B (fallback): hoja CSS hecha a mano (design tokens + componentes) sin Tailwind, si el operador prefiere cero binarios de terceros. Decidir al abrir la task.
- **Design tokens primero:** paleta extendida sobre el dark slate/emerald actual (superficies, bordes, acentos por severidad `critical→info`), escala tipográfica, radios, espaciado y sombras definidos como constantes reutilizables (CSS custom properties + preset de Tailwind en el config del CLI).
- **Layout con sidebar** (en vez del header plano actual): navegación primaria (New scan, Dashboard, History, Scopes, Users) colapsable en móvil, cabecera contextual (target/engagement activo), campana y cuenta de usuario en la zona derecha.
- **Componentes repetibles** definidos como partials Jinja2 (`templates/components/`): tarjeta, tabla, badge de severidad/confianza, botón (primario/secundario/peligro), input, modal, drawer, empty state, banner de error+Retry, esqueletos de carga. Cada página compone; nada de CSS ad-hoc por página.
- **Severidad y hallazgos como espectáculo visual:** mapa de calor en Dashboard, timeline por run, badges con significado cromático consistente (mismos tokens en `run.html`, Dashboard y exports HTML).
- **A11y no se negocia:** todo lo de TASK-20 (skip-link, trampa de foco, ARIA, teclado, contraste AA) se re-valida sobre el nuevo sistema con los mismos tests de página; los tests existentes son la regresión.

## Alcance

### 26.1 Sistema

- Pipeline de CSS compilado (Opción A o B) + tokens + partials de componentes.
- `base.html` nuevo: sidebar, header, footer, zona de cuenta (Signed in as / Sign out de TASK-24) y campana relocada. `login.html`/`register.html`/`setup.html` (TASK-25) comparten una shell centrada de "auth" con marca.

### 26.2 Páginas (en orden)

1. **Auth:** `/login`, `/register`, `/setup` — marca, flujo claro, mensajes de error consistentes.
2. **New scan (`index.html`):** wizard en pasos visuales (targets → scope → depth → confirmación), modal de confirmación rediseñado.
3. **Run (`run.html`):** página de resultados con resumen ejecutivo arriba, timeline de progreso SSE y tabla de findings con drawer rediseñado.
4. **Dashboard:** tarjetas de métricas, mapa de calor por severidad/tipo, tendencias si hay datos.
5. **History:** tabla con filtros visibles, paginación Older/Newer (TASK-21) como componente.
6. **Scopes y Users (TASK-25):** CRUD con diálogos consistentes.

### 26.3 Regresión

- Los tests de página de TASK-20 siguen verdes (adaptando selectores si cambia el DOM).
- Matriz de estados 20.1 re-verificada por página tras el rediseño.

## Contratos de datos

- Ninguno: la UI consume las mismas APIs; no se toca backend salvo `_page_context` (ya previsto en TASK-25) si el header necesita el usuario actual.

## Fuera de alcance

- Framework SPA, Node/npm en el repo, i18n, tema claro (dark-only se mantiene; los tokens dejan preparado el claro para el futuro).
- Cambios de contratos de API o de los enums de presentación.

## Tests

- `tests/integration/test_*_page.py` existentes en verde (adaptación de selectores).
- Nuevo `test_ui_system.py`: los partials renderizan (badge de severidad con las 5 clases correctas), el CSS compilado se sirve desde `/static` y no hay referencias al CDN de Tailwind en ninguna plantilla.
- Suite completa verde + ruff + cobertura ≥85%.

## Criterios de aceptación

- [ ] Ninguna plantilla carga Tailwind por CDN; todo el CSS se sirve de `/static` compilado.
- [ ] Sistema de componentes en uso: sin estilos ad-hoc duplicados entre páginas.
- [ ] Las 7+3 páginas (con las de TASK-25) rediseñadas y con la matriz de estados 20.1 re-verificada.
- [ ] Tests a11y de TASK-20 en verde sobre el nuevo DOM; contraste AA verificado.
- [ ] Suite 100% verde, ruff limpio, cobertura ≥85%; revisión supply-chain del pipeline de CSS documentada.
