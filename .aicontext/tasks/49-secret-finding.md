# TASK-49: `finding_type: secret`

**Módulo:** `detectors/secrets.py`, `detectors/patterns.py`, `detectors/registry.py`, rúbrica, guard, labels UI/CLI/reportes, Alembic  
**Spec:** [specs/49-secret-finding.md](../../specs/49-secret-finding.md)  
**Dependencias:** TASK-02, TASK-03, TASK-05, TASK-37  
**Agentes:** `pipeline-engineer` (detector + rúbrica), `llm-agent-engineer` (guard)  
**Estado:** **Cerrada 2026-11-13.**

## 1. Objetivo técnico

Emitir `finding_type: secret` cuando un valor de `RawMetadataItem` (cualquier
campo, incluidos comentarios ya extraídos) coincide con la allowlist cerrada:

- AWS access key id `AKIA` + 16 alfanuméricos
- GitHub PAT `ghp_` + 36 alfanuméricos
- cabecera PEM `BEGIN … PRIVATE KEY`
- JWT compact (`eyJ` + tres segmentos base64url acotados)

Detector `rule`, snippet anclado, `severity` NULL hasta clasificar. Techo
heurístico `critical`. El guard post-LLM rechaza si el patrón no está en el
snippet. No se reutiliza `debug_comment` para secretos limpios (sin
`TODO`/`FIXME`).

## 2. Subtareas

- Enum `secret` en contratos, modelo, Alembic Postgres `ADD VALUE`.
- `SecretDetector` sobre todos los valores extraídos; no abre bodies ni JS.
- `SECRET_RES` compartidos en `detectors/patterns.py`.
- Clasificador: patrón cerrado → `critical`; si no, `info`.
- Plantillas inglés; labels UI español / CLI y exports inglés.
- Guard: rechazo si `secret` sin patrón en `evidence_snippet`.

## 3. Fuera de alcance

Bodies, JS source, sourcemaps, JSON APIs. TruffleHog / gitleaks. Patrones
abiertos (`password=` genérico como tipo nuevo). `author_name`. Specs 50–51.

## 4. DoD

- [x] `secret` en contratos y enum; detector sin `severity`
- [x] AKIA / `ghp_` / PEM / JWT en metadata → `secret`; `password=` solo no
- [x] Comentario sin TODO con AKIA → `secret`, no `debug_comment`
- [x] Guard rechaza `secret` sin patrón en el snippet
- [x] Spec 49 closed; MEMORY y backlog actualizados
