# Característica: interfaces

**Proyecto:** MetaTracer  
**MVP:** v1.0 — imprescindible  
**Estado:** v1.0 + v1.1 (historial, filtros, CLI `show`)  
**PRD:** [volver al índice](../PRD.md)

## Resumen

Dos superficies sobre el mismo pipeline: una **Web UI** moderna y una **CLI**. Ambas soportan entrada de targets, progreso del run, resultados priorizados y exportación.

Cubre los pasos 1 y 5 del [flujo de usuario](user-flow.md). El despliegue es **local + Docker**.

## Valor para el usuario

- **CLI:** hunting diario, scripting, runs repetibles.
- **Web UI:** explorar hallazgos, mostrar el producto en un portfolio, recorrer un reporte.

## Superficies

### Web UI

- Layout atractivo y moderno (nivel portfolio, pero usable).
- Entrada: URLs/dominios, confirmación de scope, ajuste de detalle de razonamiento.
- Progreso de descarga / extracción / análisis.
- Tabla de hallazgos priorizados + detalle del hallazgo (evidencia, explicación, remediación).
- Acción de exportación (Markdown / JSON / HTML).
- Historial local de runs (`/runs`) para reabrir un scan sin repetirlo (v1.1).

### CLI

- Las mismas acciones núcleo: iniciar un run, pasar targets, fijar detalle de razonamiento, listar/reabrir (`list-runs`, `show`), exportar.
- Salida legible más un exit code que refleje éxito vs fallo del run (puede haber cero hallazgos).
- Prompts claros de modo seguro / scope salvo que el usuario ya haya confirmado el scope de ese run.

Ambas superficies llaman a los mismos servicios de aplicación; no deben bifurcar la lógica de negocio.

## Requisitos

1. Recoger targets (lista de URLs o dominios).
2. Mostrar aviso de uso responsable y exigir confirmación de scope antes de escanear ([ética](08-ethics-legal-safety.md)).
3. Mostrar resultados priorizados de [generación de reportes](04-report-generation.md).
4. Permitir exportar el run actual.
5. Ejecutarse en local y vía Docker.
6. Superficializar errores por asset sin tumbar la sesión.
7. Mantener la UI centrada: run + resultados + export + historial local. El dashboard de plataforma sigue en [v2.0](10-timeline-and-roadmap.md).

## Criterios de aceptación

- Un usuario puede completar el flujo MVP completo en la Web UI sin usar la CLI.
- Un usuario puede completar el mismo flujo en la CLI sin usar la Web UI.
- El modo seguro bloquea un escaneo hasta confirmar el scope.
- El orden de resultados coincide con el ranking de severidad del reporte.
- El arranque con Docker está documentado y funciona sin setup local de Python más allá de Docker.
- La CLI es usable en un flujo típico de terminal de hunter (flags/args, no solo un wizard interactivo).

## Fuera de alcance

| Elemento | Cuándo |
| --- | --- |
| Dashboard completo, producto de gestión de scopes, notificaciones | [v2.0](10-timeline-and-roadmap.md) |
| SaaS multi-usuario / control plane cloud alojado | No en el MVP |

## Dependencias

- **Upstream:** [Generación de reportes](04-report-generation.md), [Ética, legal y safety](08-ethics-legal-safety.md)
- **Downstream:** ninguna (fin del flujo MVP)
- **Plataforma:** [Requisitos técnicos](07-technical-requirements.md)
