# Ética, legal y safety

**Proyecto:** MetaTracer  
**PRD:** [volver al índice](../PRD.md)

## Posicionamiento

> AI-powered sensitive metadata discovery for Bug Bounty & Red Team

MetaTracer es para descubrimiento de metadata en activos públicos **autorizados**. No es un scanner weaponizado y no debe documentarse ni construirse como tal.

## Solo uso autorizado

Targets permitidos:

- Programas de bug bounty in-scope
- Auditorías con permiso **explícito**
- Assets propios

Cualquier otra cosa queda fuera del alcance del producto. No hay un “lab mode” que desactive esto en la distribución por defecto.

## Medidas de safety por defecto

| Control | Comportamiento en el MVP |
| --- | --- |
| Verificación de scope | El usuario debe confirmar scope autorizado antes de iniciar un run |
| Modo seguro | **Activo por defecto**; el escaneo no empieza hasta la confirmación |
| Rate limiting | Conservador por defecto; sin ajustes de crawl agresivo en el MVP |
| Avisos de uso responsable | Mostrados en Web UI y CLI; repetidos en reportes exportados |
| Permanecer in-scope | No descargar hosts fuera del scope confirmado (incluidos redirects off-scope) |
| Sin generación de exploits | Los agentes explican impacto y remediación; no producen payloads de exploit |

## Implicaciones de producto

- [Interfaces](06-interfaces.md) poseen la UX de confirmación.
- [Extracción de metadata](01-metadata-extraction.md) debe rechazar descargas fuera de scope.
- [Reportes](04-report-generation.md) incluyen un aviso de uso responsable.
- Los [agentes de IA](05-ai-agents.md) no pueden anular los checks de scope.

## Ética de reporte

Los hallazgos provienen de **documentos públicos que el target ya publicó**. Los reportes deben ayudar al programa a **eliminar metadata sensible**, no proporcionar recetas de ataque.
