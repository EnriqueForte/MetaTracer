# Característica: detección específica

**Proyecto:** MetaTracer  
**MVP:** v1.0 — imprescindible  
**Estado:** v1.0 + v1.2 (mismos cinco tipos)  
**PRD:** [volver al índice](../PRD.md)

## Resumen

Convertir la metadata extraída en **hallazgos tipados**: GPS/coordenadas, emails, paths internos, versiones de software y comentarios de debug.

Este es el paso 3 del [flujo de usuario](user-flow.md), después de [extracción de metadata](01-metadata-extraction.md) y antes de [clasificación de riesgo](03-risk-classification.md).

## Valor para el usuario

El hunter ve filtraciones concretas y etiquetadas, no un volcado de campos EXIF/PDF/HTML. Cada hallazgo es algo que se puede explicar y reportar. Los cinco tipos no cambian en v1.2: HTML, cabeceras y comentarios JS alimentan los mismos detectores.

## Tipos de hallazgo (MVP)

| Tipo | Qué detectar | Señales de ejemplo (ilustrativas) |
| --- | --- | --- |
| GPS / coordenadas | Datos de ubicación en metadata de imagen o documento | EXIF GPSLatitude / GPSLongitude |
| Emails | Direcciones de email en autor, creator u otros campos de metadata | `Author: jane@company.tld` |
| Paths internos | Rutas locales o internas de filesystem / UNC / home | `C:\Users\...`, `/home/...`, `\\fileserver\...` |
| Versiones de software | Producer, creator, editor, cabeceras de recon y generator HTML | PDF Producer; `http:server`; `html:meta:generator` |
| Comentarios de debug | Texto residual de debug en comment/description (incl. HTML y JS) | `html:comment` con `TODO:`; `js:comment` con `FIXME:` |

El umbral de éxito del MVP es encontrar y clasificar correctamente al menos **4–5 de estos tipos** en documentos públicos reales de dominios de prueba. Ver [criterios de éxito](09-success-criteria.md).

## Requisitos

1. Ejecutar la detección sobre metadata estructurada producida por la extracción (todos los namespaces, incluidos `http` / `html` / `js`), no sobre blobs binarios ni sobre el body HTML/JS.
2. Emitir un registro de hallazgo con al menos:
   - tipo de hallazgo (uno de los cinco anteriores)
   - ID / URL del asset de origen
   - evidencia (nombre de campo + extracto)
   - método del detector (`rule`, `heuristic`, o más adelante `agent`)
   - confianza (`high`, `medium`, `low`)
3. Preferir detectores deterministas primero (regex / parsers) para resultados reproducibles. Los agentes enriquecen y clasifican; no sustituyen la extracción.
4. Deduplicar hallazgos idénticos en el mismo asset (mismo tipo + misma evidencia).
5. No inventar hallazgos que no estén anclados en evidencia extraída.
6. Mantener el ruido no sensible fuera de la lista de hallazgos (campos vacíos, nombres genéricos de producer públicos sin versión, etc. quedan como metadata cruda, no como hallazgos).

## Criterios de aceptación

- Un set de prueba de PDFs/imágenes/HTML públicos produce hallazgos en al menos cuatro de los cinco tipos, con evidencia apuntando a un campo real de metadata.
- Los hallazgos GPS incluyen coordenadas parseables cuando existe EXIF GPS.
- Los hallazgos de email son cadenas con forma de email válidas desde la metadata, no por adivinación.
- Los hallazgos de path interno solo se marcan cuando el valor parece ruta de filesystem/UNC/home, no una URL pública.
- La evidencia duplicada en el mismo asset aparece una sola vez.
- Un documento sin señales coincidentes produce cero hallazgos y sigue registrándose como escaneado.

## Fuera de alcance

- Nuevo `finding_type` (`author_name`, secretos, CSP, CORS). Un autor con email ya dispara `email`. Ver [TASK-09](../tasks/09-source-expansion.md).
- Búsqueda de secretos/credenciales más allá de los cinco tipos (si aparecen dentro de esos campos, se tipan como uno de los cinco y se anotan en la explicación).
- Tratar cada clave de metadata como un hallazgo.

## Dependencias

- **Upstream:** [Extracción de metadata](01-metadata-extraction.md)
- **Downstream:** [Agentes de IA](05-ai-agents.md), [Clasificación de riesgo](03-risk-classification.md)
