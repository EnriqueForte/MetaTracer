# Backlog abierto (v3.4+)

Solo ítems con spec. Prioridad de producto 2026-11-12 (búsqueda y operador primero).
TASK-00–35 y specs 36–45 están **closed**. Código de 46–51: solo con spec `active` + TASK-NN.

| # | Spec | Tema | Estado | Depende de |
| :--- | :--- | :--- | :--- | :--- |
| 00 | [00-sdd-governance](00-sdd-governance.md) | Overlay SDD, MEMORY, catálogos | closed | — |
| 36 | [36-investigations](36-investigations.md) | Investigations + correlación | closed | v3.2 |
| 37 | [37-new-detectors](37-new-detectors.md) | `internal_endpoint`, `cloud_storage`, ooxml/odf | closed | v3.2 |
| 38 | [38-connectors](38-connectors.md) | Conectores egreso | closed | 15 (webhooks) |
| 39 | [39-export-redaction](39-export-redaction.md) | Redacción de exports | closed | 04/18 |
| 40 | [40-onnx-embeddings](40-onnx-embeddings.md) | Embeddings ONNX reales | closed | 23 |
| 41 | [41-ops-hygiene](41-ops-hygiene.md) | Lock, resume abort, métricas, API versioning | closed | 28/33 |
| 42 | [42-ui-operator](42-ui-operator.md) | Triage masivo, densidad, deuda de paneles | closed | 35 |
| 43 | [43-ui-investigations](43-ui-investigations.md) | UI de correlación | closed | 36 |
| 44 | [44-watch-cron](44-watch-cron.md) | Watch `--cron` UTC + unit systemd | closed | 22 |
| 45 | [45-ui-spanish](45-ui-spanish.md) | Web UI en español | closed | 42/43 |
| 46 | [46-global-search](46-global-search.md) | Búsqueda global findings + metadata | closed | 45 |
| 47 | [47-operator-workspace](47-operator-workspace.md) | Split pane hallazgos, nav, rollups | closed | 42/45 |
| 48 | [48-extraction-surface](48-extraction-surface.md) | GIF/SVG, IPTC GPS, cloud URI, CSS url | closed | 37 |
| 49 | [49-secret-finding](49-secret-finding.md) | `finding_type: secret` | reserved | enum al activar |
| 50 | [50-watch-deltas](50-watch-deltas.md) | Watch desaparecido / severity-up | reserved | 44 |
| 51 | [51-local-ingest](51-local-ingest.md) | Ingesta de carpeta local | reserved | extractores actuales |

Orden v3.4: **46–48 closed**. Siguiente: **49 → 50 → 51**.
No abrir 48+49+51 a la vez (tests negativos de safety por extractor).
