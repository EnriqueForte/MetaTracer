# Retoque visual de Web V2

**Fecha:** 2026-09-29
**Estado:** R1–R6 hechas.
**Alcance:** solo `web/`. La UI clásica (Jinja) no se toca. No hay fase 16 de migración ni corte de `/`.

Referencias miradas, no copiadas: un tablero operativo denso (riel izquierdo, una sola tinta de acento, cifras arriba, barras de etapa, ranking y tabla) y un tablero violeta de plantilla (aros de arcoíris, calendario, “lorem”, porcentajes decorativos). Del primero se toma la densidad y la jerarquía. Del segundo no se toma nada.

La dirección de [v2-visual-direction.md](v2-visual-direction.md) sigue vigente: acero, severidad apagada, sin neón, sin grafo, sin chat.

## Qué está mal ahora

Las pantallas de `/v2` son columnas de tarjetas iguales, títulos en mayúsculas espaciadas y el mismo `gap` en wizard, dashboard y run. Las barras de severidad salen todas en el color de acento. Eso se lee como plantilla, no como una consola de un scan.

## Qué se puede dibujar

Solo números que ya devuelve el API:

| Superficie | Datos reales |
| :--- | :--- |
| Dashboard | `runs`, `findings` (total, unclassified, `severity_breakdown`, `by_type`), `assets`, `top_domains`, `top_evidence`, `agent_usage` |
| Run | siete etapas SSE, asset en curso, findings en orden del API, issues, cinco exports |
| History | runs, estado (incluido `aborted`), cursores |
| Campana | notificaciones ya existentes |

No hay serie temporal en `GET /api/stats`. No se inventa un gráfico de línea, un donut, un calendario ni un “objetivo”. Si un número no está en la respuesta, no se pinta.

## Reglas del retoque

- Un acento: el acero `--mt-accent`. El naranja y el violeta de las referencias no entran.
- La severidad usa su color ya definido (critical, high, medium, low, info, unclassified). No se unifica en acero.
- El texto del target, la prosa del modelo y los errores siguen siendo nodos de texto. Sin `dangerouslySetInnerHTML`.
- El modal de scope no cambia de comportamiento: checkbox desmarcado, una sola fuente, sin `watch`.
- Movimiento solo al cambiar un estado (etapa, fila, número). Sin partículas ni brillos.
- Nada de páginas nuevas: knowledge, webhooks, watch, chat, CVSS.

## Fases

Cada fase termina con Vitest en verde, las plantillas de V1 sin diff y una nota corta. Si el CSS de producción ganara `unsafe-eval` o un origen de terceros, se para y entra `safety-guardian`.

### R0 — Contrato

Este documento y el agente `v2-ui-engineer`. Sin pantallas.

### R1 — Shell

Riel con la ruta activa marcada por el acero, no por un bloque naranja. Barra superior más baja: aviso ético en una línea, campana, sesión. El pie ético y el enlace Classic UI se quedan. Se bajan las mayúsculas espaciadas.

### R2 — Dashboard

Fila de cuatro cifras (runs, findings, assets, tokens) con el subtexto que ya existe. Debajo, barras horizontales de severidad con su color, ranking de tipos y de dominios, tabla de evidencia repetida. El uso del agente queda en una franja inferior, no como héroe. Vacío: un solo estado, sin ilustración decorativa.

### R3 — Run

Las siete etapas en una fila horizontal, con la activa distinguida. La tabla de findings más densa. El drawer sigue siendo el sitio de la prosa y del feedback. Exports en la misma barra, no en una tarjeta aparte.

### R4 — Wizard

El formulario largo pasa a una barra de comando: targets, scope, profundidad y Start scan en una sola franja. El modal de confirmación no se rediseña de lógica. Los textos de 403, 404, 409 y 429 se conservan.

### R5 — History, scopes, users

Las tres listas usan la misma densidad de tabla que el dashboard. Sin columnas nuevas. El código de invitación sigue mostrándose una vez, como texto.

### R6 — Auth

Login, registro y setup comparten la superficie del shell (fondo, tipo, un panel), sin riel. No se convierten en una landing.

## Quién lo hace

`v2-ui-engineer` implementa R1–R6. `ui-engineer` y `ui-architect` no entran: su mandato prohíbe React y les exige no proponer Next. `safety-guardian` revisa el diff si se toca CSP, `safeUrl`, el modal de scope o una dependencia. `docs-architect` cierra la nota de cada fase.
