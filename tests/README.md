# MetaTracer test suite

Layout and marks (TASK-07, subtask 7.2):

| Path | Mark | What runs here |
| :--- | :--- | :--- |
| `tests/unit/` | `unit` | Fast single-module tests (incl. HTML/JS/header extractors from TASK-09). |
| `tests/agents/` | `unit` | Agent layer with a mocked LLM — zero real network. |
| `tests/integration/` | `integration` | Multi-module tests; faked transport or the loopback mock origin. |
| `tests/integration/test_e2e_pipeline.py` | `integration` + `e2e` | Full pipeline over real loopback HTTP. |

Marks are auto-applied by directory in `tests/conftest.py`; the `e2e` mark lives
in the e2e module itself. `slow` is registered for future use.

```powershell
# Fast loop (CI PR): everything except e2e
.venv\Scripts\python.exe -m pytest -m "not e2e"

# Full suite (CI main / local)
.venv\Scripts\python.exe -m pytest
```

## `METATRACER_ALLOW_LOOPBACK` — TEST ONLY

The e2e tests scan a **real local mock origin** (uvicorn on `127.0.0.1`, ephemeral
port, see `tests/fixtures/mock_origin.py`). The `NetworkSafetyGuard` blocks
loopback by default, so the e2e constructs `Settings(allow_loopback=True)` — the
in-process equivalent of `METATRACER_ALLOW_LOOPBACK=true`.

This flag exists **only for this suite**: never in the product default, the
Docker image, the Compose file or any deployment. One e2e test
(`test_loopback_origin_is_rejected_without_the_test_flag`) proves the default
still refuses the mock origin before opening any socket.

Never point the suite at third-party sites: every test target is either the
in-memory `httpx.MockTransport` or the local mock origin serving the synthetic
fixtures from `tests/fixtures/generate_test_fixtures.py` (synthetic domain
`acme-corp.internal`; `.test` is not a mailbox). Regenerate the on-disk copies with:

```powershell
.venv\Scripts\python.exe -m tests.fixtures.generate_test_fixtures
```

## Coverage gate (DoD)

`metatracer.core`, `metatracer.detectors`, `metatracer.extractors` and
`metatracer.reports` must each stay **>= 85%**. Measure with:

```powershell
.venv\Scripts\python.exe -m pytest --cov=metatracer.core --cov=metatracer.detectors `
  --cov=metatracer.extractors --cov=metatracer.reports --cov-report=term-missing
```

The `agents` package is intentionally excluded from the gate (LLM-mocked code);
do not inflate the number with trivial prompt tests.
