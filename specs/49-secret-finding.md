# Spec 49 — `finding_type: secret`

**Estado:** closed  
**Agente previsto:** `pipeline-engineer` · rúbrica: skill `risk-rubric` · guard LLM:
`llm-agent-engineer` si el clasificador/agente toca el tipo  
**Skill al abrir:** `detector-patterns`, `risk-rubric`  
**Task:** [TASK-49](../.aicontext/tasks/49-secret-finding.md)

## Intención

El clasificador ya puede **subir** un `debug_comment` a `critical` si el snippet
contiene `password=`, `AKIA…`, `ghp_`, PEM. Un secreto en metadata o comentario
**sin** `TODO:`/`FIXME:` no dispara detector → falso negativo. La auditoría
2026-10-03 y TASK-34 dejaron `secret` fuera a propósito.

Esta slice añade el tipo **con contrato primero**. Mientras esté `reserved`, el
enum **no** cambia y el código **no** emite `secret`.

## Contrato (al pasar a `active`, en este orden)

1. Añadir `secret` a `finding_type` en `.aicontext/tasks/README.md` y
   `.cursor/rules/data-contracts.mdc`. Techo de rúbrica: `critical`.
2. TASK-49: detector `rule` sobre **valores de `RawMetadataItem` y comentarios**
   ya extraídos. Allowlist cerrada de patrones (p. ej. AWS key id `AKIA`, GitHub
   PAT `ghp_`, cabecera PEM, JWT compact). Snippet anclado; `severity` NULL hasta
   clasificar.
3. Guard post-LLM: no inventar; rechazar si el patrón no está en
   `evidence_snippet`. No exploits, no payloads.
4. UI/CLI/reportes: un valor más en filtros y charts existentes (español en UI,
   inglés en exports).

## Fuera de alcance

Secret-scanning de bodies, de JS source, de sourcemaps, de JSON APIs.
TruffleHog / gitleaks como dependencia. Nuevos patrones abiertos (“cualquier
password”). `author_name`. Código o enum mientras esta spec esté `reserved`.

## Dependencias

Spec 37 closed (no duplicar `cloud_storage`). ADR-0009 (`author_name` sigue sin
ser finding). Clasificador actual: no reutilizar `debug_comment` para secretos
limpios una vez exista el tipo.
