# Característica: generación de reportes

**Proyecto:** MetaTracer  
**MVP:** v1.0 — imprescindible  
**Estado:** v1.0 + v1.1 (export HTML)  
**PRD:** [volver al índice](../PRD.md)

## Resumen

Producir **reportes estructurados, priorizados y exportables** que un hunter enviaría de verdad a un programa de bug bounty.

Este es el paso 5 del [flujo de usuario](user-flow.md).

## Valor para el usuario

La salida es un write-up de finding, no un volcado de metadata: qué se filtró, dónde, por qué importa y cómo remediarlo.

## Contenido del reporte (MVP)

Cada hallazgo del reporte debe incluir:

| Sección | Propósito |
| --- | --- |
| Título | Declaración de filtración en una línea |
| Severidad | Critical / High / Medium / Low / Info |
| Asset | URL de origen / dominio / tipo de archivo |
| Tipo de hallazgo | GPS, email, path interno, versión de software o comentario de debug |
| Evidencia | Nombre del campo de metadata + extracto (sin datos inventados) |
| Impacto | Por qué puede importar en un contexto OffSec / bounty |
| Explicación | Generada por el agente, anclada en evidencia; la verbosidad sigue el ajuste del usuario |
| Remediación | Consejos prácticos de higiene de metadata (quitar EXIF, sanitizar info PDF, no publicar comentarios de debug, regenerar exports) |
| Repro (no explotativo) | Cómo abrir el asset público e inspeccionar el mismo campo (`exiftool` / `pdfinfo` / `curl`) — no un exploit |

El reporte completo también incluye: recordatorio de target/scope, timestamp del run, conteos por severidad y un aviso de uso responsable.

## Requisitos

1. Mostrar un reporte priorizado en la [Web UI](06-interfaces.md).
2. Exportar el mismo reporte en Markdown, JSON y HTML (v1.1). JSON sirve a tooling; el HTML se imprime a PDF si hace falta.
3. Incluir solo hallazgos anclados en evidencia de extracción/detección.
4. Respetar el nivel de detalle de razonamiento configurado en [agentes de IA](05-ai-agents.md).
5. Hacer reportes legibles para un triager de programa que no ejecutó la herramienta.
6. Umbral de éxito: reportes **que tú enviarías**. Ver [criterios de éxito](09-success-criteria.md).

## Criterios de aceptación

- Un run con severidades mixtas muestra Critical/High primero.
- La exportación contiene los mismos hallazgos y severidades que la UI.
- Cada hallazgo tiene evidencia que apunta a un campo real de metadata del asset.
- Los reportes incluyen remediación y una vía de reproducción no explotativa.
- Los runs vacíos producen un reporte válido de “sin hallazgos”, no un error.
- Los reportes incluyen un aviso de que el escaneo debe permanecer en scope autorizado.

## Fuera de alcance

| Elemento | Cuándo |
| --- | --- |
| Exportación PDF nativa (nueva dependencia runtime) | No (cadena de suministro cerrada; el HTML de v1.1 se imprime a PDF) |
| Dashboard completo y notificaciones | [v2.0](10-timeline-and-roadmap.md) |
| Auto-envío a HackerOne / Bugcrowd / etc. | No planificado |

## Dependencias

- **Upstream:** [Clasificación de riesgo](03-risk-classification.md), [Agentes de IA](05-ai-agents.md)
- **Downstream:** [Interfaces](06-interfaces.md)
