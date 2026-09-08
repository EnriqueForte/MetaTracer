# Referencias e inspiración

**Proyecto:** MetaTracer  
**PRD:** [volver al índice](../PRD.md)

## Referencia directa

- **[MetaHunter (Acorzo1983)](https://github.com/Acorzo1983/Metahunter)** — punto de partida. Suite de helpers de recon en Python (descarga de PDF, extracción de metadata de PDF, harvest de emails / construcción de diccionarios) orientada a information disclosure en bug bounty.

MetaTracer **no** es un fork con otro nombre. Usar MetaHunter como baseline de “el recon de metadata existe” y luego superarlo.

## Cómo MetaTracer debe ir más allá

| Baseline estilo MetaHunter | MetaTracer MVP |
| --- | --- |
| Metadata de PDF / harvest de email centrado en scripts | PDF, imágenes, HTML, cabeceras HTTP de recon y comentarios JS |
| Flujo de producto limitado | Ciclo completo de finding: detectar → clasificar → reportar |
| Poca/ninguna IA | Agentes LangGraph con razonamiento configurable y límites de contexto |
| Sin mandato de doble UX | Web UI + CLI sobre un pipeline |
| Safety dejada al operador | Check de scope, rate limits, modo seguro activo por defecto |

## Inspiración adyacente (no son dependencias)

- Problemas clásicos de higiene de metadata EXIF/PDF en archivos públicos (el problem space).
- Estructura de reportes de bug bounty (evidencia clara, impacto, remediación).
- Diseños de agent-graph que mantienen las tools deterministas y los LLMs interpretativos.

No incorporar proyectos no relacionados que compartan el nombre “MetaHunter” (indexadores de filesystem, frameworks binarios, etc.).
