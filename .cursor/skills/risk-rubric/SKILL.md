---
name: risk-rubric
description: Rúbrica de severidad de MetaTracer (5 niveles, techos por tipo, anclaje anti-alucinación) y su uso dual en el clasificador heurístico y en el guard post-LLM. Usar al tocar classification/rubric.py, classification/classifier.py, classification/templates.py, classification/anchor.py, reports/builder.py (orden y labels) o los prompts y validadores de agents/.
---

# Rúbrica de severidad

**Skill de doble dueño.** La misma rúbrica alimenta el heurístico (offline,
siempre disponible) y el agente (prompt + guard). Un cambio aquí afecta a
**ambos lados** y debe mantenerlos coherentes. Fuente: `.aicontext/tasks/03-risk-classification.md`
y `.aicontext/tasks/05-ai-agents.md`.

## Orden y niveles

`SEVERITY_RANK` (`rubric.py`): `info`=0, `low`=1, `medium`=2, `high`=3, `critical`=4.
Los detectores **nunca** asignan severity: es `NULL` hasta que clasifica el
heurístico (TASK-03) o el agente (TASK-05).

## Techos heurísticos obligatorios (`HEURISTIC_CEILINGS`)

| Tipo | Techo | Motivo |
| :--- | :--- | :--- |
| `gps` | `high` | El snippet son coordenadas; no hay domicilio, persona ni instalación. `critical` es **inalcanzable** por diseño. |
| `email` | `medium` | Un email corporativo es a lo sumo medium. |
| `internal_path` | `high` | Usuario/UNC sí; `/var/www` sin usuario no. |
| `software_version` | `low` | Un nombre+versión no prueba explotabilidad. |
| `internal_endpoint` | `medium` | Dirección interna en metadata; no es un acceso demostrado. |
| `cloud_storage` | `high` | La URL se registra y no se pide. |
| `debug_comment` | `critical` | **Solo** con marcador de secreto en el snippet. |

`cap_severity(sev, ceiling)` baja al techo cuando el rank lo supera. El guard
post-LLM usa **el mismo** `ceiling_for(type)`.

## Lo que sostiene cada nivel

- **critical**: hay un **valor** de secreto en el snippet. `_SECRET_VALUE_RE`:
  `password|token := valor`, `api_key := valor`, `AKIA[0-9A-Z]{16}`,
  `ghp_[A-Za-z0-9]{36}`, `-----BEGIN … PRIVATE KEY-----`.
  **No** basta la palabra suelta (`_SECRET_RE`): "remove staging credentials"
  es un marcador, se queda en medium. `CONFIDENTIAL` tampoco.
- **high**: ruta interna con usuario o UNC (`C:\Users\…`, `\\CORP-DC01\…`),
  o coordenadas GPS precisas.
- **medium**: email corporativo personal (`nombre.apellido@empresa.com`);
  comentario que referencia proyecto/ticket/staging (`JIRA-8812`); ruta Unix
  genérica de despliegue (`/var/www/intranet`).
- **low**: nombre de software con versión y nada más (`Apache FOP 2.4`);
  buzón de rol publicado (`info@`, `contact@`) — canal de contacto, no fuga.
- **info**: evidencia vacía, genérica o débil (`DRAFT` aislado, cadenas
  ambiguas). Nunca inflar "por si acaso".

## Anclaje anti-alucinación (`classification/anchor.py`)

- Snippet vacío o que **no es substring** de la metadata → `info`.
- Ante ambigüedad, **un nivel menos**.
- Prohibido subir severidad sin texto del snippet que lo justifique.
- Sin OSINT, sin geocoding, sin lookup de CVEs: el contexto sale del snippet,
  `field_source`, content-type y dominio, nunca de conocimiento externo.

## Determinismo y plantillas

- `classify_heuristically()` es **puro**: sin I/O, mismos inputs → misma salida.
- La prosa sale de plantillas fijas en inglés por tipo+nivel
  (`classification/templates.py`), no del modelo. Repro **no explotativa**
  (`exiftool` / `pdfinfo` / `curl` sobre el archivo público).
- `reports/builder.py` ordena por `_SEVERITY_ORDER` (critical 5 → info 1) y
  deja los **NULL al final** (rank 0). No confundir con `SEVERITY_RANK`.

## Uso en el agente (TASK-05)

- `RUBRIC_PROMPT_TEXT` (`rubric.py`) se **embebe literal** en el system prompt.
  Es la representación en inglés de esta misma rúbrica: si cambias una, cambia
  la otra en el mismo commit.
- El guard (`agents/guard.py`) solo puede **bajar o rechazar**:
  techo por tipo, severidad soportada por el snippet (re-derivada con el
  heurístico) y baseline del operador (feedback) como cota.
- Incoherencia texto↔severidad (la prosa cita otro nivel) → se rechaza y cae
  al heurístico.

## Cuándo parar y preguntar

Si el cambio exige un nivel nuevo, otro `finding_type` o mover un techo,
**para**: primero se actualiza `.aicontext/tasks/README.md` (contratos
cerrados). Un enum nuevo sin contrato es bloqueante.

## Checklist

- [ ] `HEURISTIC_CEILINGS` y `RUBRIC_PROMPT_TEXT` cuentan lo mismo.
- [ ] Ningún detector asigna severity.
- [ ] El snippet soporta el nivel (anclaje); ambiguo ⇒ un nivel menos.
- [ ] `critical` exige **valor** de secreto, no la palabra.
- [ ] GPS sigue con techo `high`.
- [ ] Cambio de orden/labels actualizado en `reports/builder.py`.
- [ ] Test del clasificador que cubre el caso límite que motivó el cambio.
