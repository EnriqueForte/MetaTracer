# Dirección visual de Web V2

Aceptada junto con [ADR-001](ADR-001-nextjs-react-migration.md) el 2026-09-26. Obliga a las fases de UI del [plan](../migrations/v1-to-v2-frontend.md). No obliga a Web V1: `.aicontext/ui/*` sigue siendo el contrato Jinja.

Referencia observada: demo BugTrace (`https://demo.bugtraceai.com/bugtraceai`), revisión del 2026-09-26. Se toma la estructura de trabajo. No se toma el catálogo de producto ni la marca.

## Qué se adopta

La pantalla de trabajo es un lienzo, no un formulario largo.

1. **Barra de comando** arriba: targets, una sola fuente de scope, profundidad de razonamiento, acción primaria compacta. El modal de scope sigue siendo un gate: checkbox desmarcado, sin POST hasta confirmar.
2. **Canvas** debajo. Vacío: un estado gráfico breve (“Awaiting scan data”), no un párrafo suelto. Con `run_id`: las siete etapas del SSE, el asset en curso y el mensaje, como texto.
3. **Al terminar el run**, el mismo sitio muestra el resumen y la tabla. Barras Critical → Info y el total salen de los findings ya devueltos, o de `GET /api/stats` en el dashboard. No hay métricas nuevas.
4. **Fila expandible** con los campos que ya existen: evidencia en monoespacio; aparte, justificación, impacto, remediación y pasos de reproducción. Todo texto. `safeUrl` en los enlaces de asset.
5. **History** como tabla de runs. **Descargas** en los cinco formatos actuales (`md`, `json`, `html`, `csv`, `bounty`).
6. **Movimiento** solo al cambiar de estado: etapa SSE, apertura de fila, aparición del resumen. Sin partículas, sin neón, sin grafos decorativos.

La navegación sigue siendo la de MetaTracer: Dashboard, Reconnaissance, History, Scopes, Users. No se sustituye por la suite de diez herramientas de la demo.

Severidad: se conservan las etiquetas con texto y la escala ya definida (Critical apagado, High cobre, Medium ámbar, Low acero, Info gris, Unclassified sin relleno). El acento de acción sigue siendo el acero de `--mt-accent`, no el naranja de la demo. Un clon de su violeta haría que MetaTracer parezca otro producto.

## Qué no se adopta

| Elemento de la demo | Motivo |
| :--- | :--- |
| Chat, AIrepeater, Model Lab, Payload Tools, JWT Analyzer, PrivEsc, File Upload Auditor | No hay API ni flujo en MetaTracer |
| Grafo “swarm” / attack graph | No hay contrato de grafo. Split = etapas + findings. Events = el `ProgressEvent` que ya emite el bus |
| CVSS, petición/respuesta de exploit, “Proof of exploitation” | MetaTracer no calcula CVSS y el agente no genera payloads |
| Depth 5 y Max URLs 500 | Esos controles no existen. El crawl lo decide el backend |
| Selector de proveedor LLM | La configuración del modelo sigue en el servidor |
| ZIP / YAML de la demo | Los formatos de export ya están cerrados |

`aborted` y `failed` se distinguen con `GET /api/runs/{id}` después de la etapa SSE `failed`. El canvas no inventa un tercer estado.

## Dónde se construye

Fases 5 a 10 del plan de migración, dentro de `web/`. Esas fases ya están construidas. No se aplica a las plantillas Jinja.

El retoque de densidad y jerarquía, sin copiar las referencias de tablero, está en [v2-ui-refresh.md](v2-ui-refresh.md). Lo implementa `v2-ui-engineer`, no `ui-engineer`.
