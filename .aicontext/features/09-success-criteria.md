# Criterios de éxito del MVP

**Proyecto:** MetaTracer  
**PRD:** [volver al índice](../PRD.md)

El MVP solo se considera exitoso si se cumplen **las tres** barras.

## 1. Hallazgos reales en dominios de prueba

La herramienta encuentra y clasifica correctamente al menos **4–5 tipos reales de hallazgos** en documentos públicos de dominios de prueba.

Tipos definidos en [detección específica](02-specific-detection.md):

- GPS / coordenadas
- Emails
- Paths internos
- Versiones de software
- Comentarios de debug

“Correctamente” significa: la evidencia coincide con un campo real de metadata, la severidad sigue [clasificación de riesgo](03-risk-classification.md) y la explicación no inventa hechos.

## 2. Reportes que tú enviarías

[Generación de reportes](04-report-generation.md) produce write-ups **que usarías o enviarías de verdad** a un programa de bug bounty: estructurados, priorizados, con evidencia, impacto y remediación.

Un volcado de metadata con un párrafo de LLM pegado **no** basta.

## 3. Arquitectura explicable

La arquitectura es limpia, documentada y puedes recorrerla en una entrevista técnica:

- límites entre ingest vs detect vs agent vs report
- flujo LangGraph
- por qué SQLite ahora y Postgres+pgvector después
- cómo se mantiene el contexto pequeño para reducir alucinaciones

Ver [requisitos técnicos](07-technical-requirements.md), [agentes de IA](05-ai-agents.md) y el [walkthrough de diez minutos](../walkthrough.md).

## Mapeo

| Criterio | Características |
| --- | --- |
| 4–5 tipos de hallazgos | [Detección específica](02-specific-detection.md), [Clasificación de riesgo](03-risk-classification.md) |
| Reportes enviables | [Generación de reportes](04-report-generation.md) |
| Arquitectura explicable | [Agentes de IA](05-ai-agents.md), [Requisitos técnicos](07-technical-requirements.md) |

## Verificación sugerida (no es alcance extra de producto)

Usar un set pequeño de fixtures **autorizados** (assets propios o archivos de prueba explícitamente públicos) que cubran los cinco tipos de hallazgo. No tratar sitios de producción de terceros al azar como fixtures de prueba sin scope.
