# Característica: clasificación de riesgo

**Proyecto:** MetaTracer  
**MVP:** v1.0 — imprescindible  
**Estado:** Especificada  
**PRD:** [volver al índice](../PRD.md)

## Resumen

Asignar **Critical / High / Medium / Low / Info** a cada hallazgo para poder priorizar el reporte.

Forma parte del paso 4 del [flujo de usuario](user-flow.md). Los [agentes de IA](05-ai-agents.md) realizan la clasificación; este archivo define la escala y las reglas que deben seguir.

## Valor para el usuario

Los hunters dedican tiempo a hallazgos que pueden importar en un reporte de bug bounty, en lugar de a una lista plana de campos de metadata.

## Niveles de severidad

| Nivel | Significado | Ejemplos típicos en metadata |
| --- | --- | --- |
| Critical | Exposición directa de alto impacto (secretos, ubicación sensible precisa de personas, datos tipo credenciales en metadata) | Claves privadas, passwords, tokens guardados por accidente en campos de metadata |
| High | Filtración sensible fuerte, probablemente útil para un atacante | GPS preciso de ubicación privada/hogar; paths internos que revelan usernames + infraestructura interna |
| Medium | Recon útil que ayuda a mapear superficie de ataque | Emails de empleados; versiones detalladas del stack interno; comentarios de debug con contexto interno |
| Low | Fuga débil o común con impacto limitado por sí sola | Cadenas genéricas de producer/versión; nombres de autor públicos sin contexto interno |
| Info | Metadata esperada o no sensible | Campos vacíos/estándar, producer de CMS público sin contexto extra |

La severidad depende del **contexto**, no solo del tipo de hallazgo. Un GPS en una foto de marketing de la sede pública no es lo mismo que un GPS en el escaneo de un DNI de empleado.

## Requisitos

1. Cada hallazgo de [detección específica](02-specific-detection.md) recibe exactamente una severidad.
2. La clasificación debe citar evidencia ya extraída (campo + extracto). Sin anclaje, no hay severidad.
3. La salida debe incluir:
   - severidad
   - justificación breve
   - notas de impacto opcionales para el reporte
4. El ranking en UI/CLI/export es primero por severidad (Critical → Info) y luego por confianza.
5. Si la evidencia es débil o ambigua, clasificar **más bajo** (evitar inflar la severidad).
6. Los agentes pueden proponer severidad; la rúbrica documentada (este archivo) es la fuente de verdad para revisión y tests.

## Criterios de aceptación

- Todos los hallazgos de un run tienen una severidad de la escala de cinco niveles.
- Dos hallazgos del mismo tipo pueden recibir severidades distintas cuando el contexto difiere (p. ej. path público vs interno).
- La evidencia ambigua no se marca Critical/High sin justificación ligada a evidencia.
- Reportes y UI ordenan por severidad.
- Un revisor puede ver por qué se eligió un nivel en un párrafo corto.

## Fuera de alcance

- Scoring CVSS (no requerido en el MVP).
- Envío automático a plataformas de bug bounty.
- Cambiar la severidad según tablas de payout del vendor.

## Dependencias

- **Upstream:** [Detección específica](02-specific-detection.md), [Agentes de IA](05-ai-agents.md)
- **Downstream:** [Generación de reportes](04-report-generation.md)
