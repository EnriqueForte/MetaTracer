# Usuarios objetivo

**Proyecto:** MetaTracer  
**PRD:** [volver al índice](../PRD.md)

## Audiencia

| Usuario | Contexto | Qué necesita |
| --- | --- | --- |
| Bug bounty hunter individual | Solo, con tiempo limitado, programas in-scope | Runs rápidos por CLI, evidencia, un write-up que pueda pegar en el programa |
| Red Team / Offensive Security | Engagement de equipo con permiso explícito | Runs locales repetibles, severidad consistente, reportes que un lead pueda revisar |

## Jobs to be done

1. **Dame documentos públicos in-scope y dime qué se filtró en la metadata.**
2. **Ordénalo para saber qué merece reportarse.**
3. **Dame un write-up estructurado con evidencia y remediación.**

## Implicaciones para el producto

- El flujo de una sola persona debe funcionar de extremo a extremo (sin features de equipo obligatorias en el MVP).
- Los reportes deben ser comprensibles para un triager de bounty que no ejecutó MetaTracer.
- **CLI** = uso diario; **Web UI** = exploración + demostración de portfolio. Ambas son imprescindibles en el MVP. Ver [interfaces](06-interfaces.md).
- Los defaults de safety importan para ambos públicos: el hunter puede estar cansado; el Red Team necesita auditabilidad. Ver [ética](08-ethics-legal-safety.md).

## No-usuarios (MVP)

- Analistas SOC blue-team que esperen alertas/integraciones SIEM (posible más adelante).
- Desarrolladores que busquen un wrapper genérico de librería PDF sin flujo OffSec.
- Quien apunte a sistemas sin autorización.
