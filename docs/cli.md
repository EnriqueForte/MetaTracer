# Guía de la CLI

[Volver al README](../README.md)

## CLI útil

```bash
.venv/bin/python -m metatracer scan example.com -s example.com -y
.venv/bin/python -m metatracer watch <scope-id> --once
.venv/bin/python -m metatracer watch <scope-id> --interval 21600 --webhook <webhook-id>
.venv/bin/python -m metatracer findings triage <finding-id> --status false_positive
```

`watch` reescanea un scope guardado y reporta deltas (`new_findings`,
`resolved_findings`, `severity_up_count`) **sin** mandar evidencia al webhook.

Para consultar las opciones completas ejecuta `python -m metatracer --help` o añade `--help` a un comando. Los ejemplos requieren autorización para el alcance indicado; sustituye `example.com` por un dominio autorizado. En Windows utiliza `.venv\Scripts\python.exe`.
