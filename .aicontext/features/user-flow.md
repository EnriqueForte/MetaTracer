# Flujo de usuario principal (MVP)

**Proyecto:** MetaTracer  
**PRD:** [volver al índice](../PRD.md)

## Happy path

```text
Confirmar scope (modo seguro)
        ↓
Proporcionar URLs y/o dominios
        ↓
Descubrir y descargar assets públicos (PDF, imagen, HTML, JS; rate-limited)
        ↓
Extraer metadata estructurada (incl. cabeceras HTTP allowlist)
        ↓
Detectar tipos de hallazgo (GPS, emails, paths, versiones, comentarios de debug)
        ↓
Agentes LangGraph analizan → clasifican riesgo → explican
        ↓
Reporte priorizado en Web UI + exportación
```

## Pasos

| # | Usuario / sistema | Detalle | Característica |
| --- | --- | --- | --- |
| 0 | El usuario confirma scope autorizado | Modo seguro activo por defecto; se muestra aviso | [Ética](08-ethics-legal-safety.md), [Interfaces](06-interfaces.md) |
| 1 | El usuario proporciona URLs o dominios | Entrada por lista vía Web o CLI | [Interfaces](06-interfaces.md) |
| 2 | La herramienta descarga assets públicos | PDFs, imágenes, página HTML y `.js` in-scope | [Extracción de metadata](01-metadata-extraction.md) |
| 3 | Extrae metadata y detecta hallazgos | Campos estructurados → hallazgos tipados | [Extracción](01-metadata-extraction.md), [Detección](02-specific-detection.md) |
| 4 | Los agentes analizan, clasifican y explican | Detalle de razonamiento configurable | [Agentes de IA](05-ai-agents.md), [Clasificación](03-risk-classification.md) |
| 5 | El usuario revisa y exporta | Reporte ordenado por severidad | [Reportes](04-report-generation.md), [Interfaces](06-interfaces.md) |

## Configuración

- **Detalle de razonamiento:** `brief` / `standard` / `detailed` (por defecto `standard`).
- **Scope / modo seguro:** debe cumplirse antes del paso 2.

## Casos borde

| Situación | Comportamiento esperado |
| --- | --- |
| Host fuera de scope en la lista | Omitir con motivo claro; no descargar |
| URL caída o no documento | Fallo por asset; el run continúa |
| `.pdf`/imagen que devuelve HTML | `unsupported_type`; no se recicla como asset HTML |
| Sin hallazgos | Reporte vacío válido |
| LLM no disponible | Conservar hallazgos extraídos; marcar análisis como pendiente o usar fallback |
| El usuario aborta | Persistir estado parcial del run cuando sea práctico |

## Mapeo a características

| Paso | Característica |
| --- | --- |
| 1–2 | [Extracción de metadata](01-metadata-extraction.md) (ingesta de fuentes) |
| 3 | [Extracción de metadata](01-metadata-extraction.md) + [Detección específica](02-specific-detection.md) |
| 4 | [Agentes de IA](05-ai-agents.md) + [Clasificación de riesgo](03-risk-classification.md) |
| 5 | [Generación de reportes](04-report-generation.md) + [Interfaces](06-interfaces.md) |
