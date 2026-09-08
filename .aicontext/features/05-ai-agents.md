# Característica: agentes de IA

**Proyecto:** MetaTracer  
**MVP:** v1.0 — imprescindible  
**Estado:** Especificada  
**PRD:** [volver al índice](../PRD.md)

## Resumen

Agentes orquestados con LangGraph que **analizan hallazgos, clasifican el riesgo y redactan explicaciones**. No sustituyen la extracción/detección determinista.

Este es el paso 4 del [flujo de usuario](user-flow.md). El detalle del razonamiento es **configurable**.

## Valor para el usuario

El hunter obtiene una severidad justificada y una explicación lista para reporte, no un volcado crudo de EXIF. La verbosidad configurable sirve tanto para triage rápido como para walkthroughs de calidad de entrevista.

## Responsabilidades de los agentes (MVP)

| Responsabilidad | Entrada | Salida |
| --- | --- | --- |
| Analizar | Hallazgos estructurados + evidencia | Interpretación de qué se filtró y en qué contexto |
| Clasificar | Hallazgo + análisis | Severidad según [clasificación de riesgo](03-risk-classification.md) |
| Explicar | Hallazgo + clasificación | Prosa de reporte (impacto, remediación, razonamiento anclado) |

Los detectores deterministas poseen “qué string/campo se encontró”. Los agentes poseen “qué significa y cuán grave es”.

## Requisitos

1. Orquestar el grafo con **LangGraph** ([requisitos técnicos](07-technical-requirements.md)).
2. Usar **Kimi** para análisis/clasificación compleja. Usar modelos más baratos/rápidos para tareas simples (resúmenes, formato, copy de bajo riesgo).
3. El detalle de razonamiento es configurable por el usuario (p. ej. `brief` / `standard` / `detailed`). El default debe servir para un reporte de bounty (`standard`).
4. **La optimización de contexto es obligatoria:**
   - Pasar solo hallazgos estructurados y extractos cortos de evidencia — nunca PDFs/imágenes crudos ni el body HTML/JS.
   - Limitar campos por asset (descartar claves vacías/duplicadas).
   - Deduplicar antes de llamar al modelo.
   - Agrupar hallazgos similares cuando no perjudique la precisión.
   - Instruir al modelo a citar evidencia; rechazar o degradar respuestas que añadan hechos no presentes en el payload.
5. Persistir las salidas del agente (severidad, explicación, modelo usado, prompt/run id) junto al hallazgo para depuración y entrevistas.
6. Si el modelo no está disponible, conservar los resultados de detección por reglas y marcar clasificación/explicación como pendiente o fallback — no perder hallazgos extraídos.

## Criterios de aceptación

- Un hallazgo con evidencia GPS recibe una explicación que menciona las coordenadas/campo reales, no ubicaciones inventadas.
- Cambiar el detalle de razonamiento cambia la longitud de la explicación, no la evidencia subyacente.
- El contexto del agente en un run no incluye binarios de archivos.
- Campos alucinados (no presentes en la metadata extraída) no se aceptan en el reporte.
- La clasificación compleja usa el modelo fuerte configurado; el formato trivial puede usar el modelo barato.
- El flujo del grafo se puede explicar: detectar → analizar → clasificar → explicar → reportar.

## Fuera de alcance

| Elemento | Cuándo |
| --- | --- |
| RAG, feedback loop, integraciones extra | [v2.1+](10-timeline-and-roadmap.md) |
| Decisiones autónomas de escaneo que omitan checks de scope | Nunca |
| Agentes que escriban payloads de exploit | Nunca |

## Dependencias

- **Upstream:** [Detección específica](02-specific-detection.md)
- **Downstream:** [Clasificación de riesgo](03-risk-classification.md), [Generación de reportes](04-report-generation.md)
- **Plataforma:** [Requisitos técnicos](07-technical-requirements.md)
