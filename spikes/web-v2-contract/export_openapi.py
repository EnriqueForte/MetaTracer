"""Dump the live FastAPI OpenAPI document without starting the server.

The orjson wheel in this environment is blocked by application control, so a
stub is registered before FastAPI imports it. OpenAPI generation does not
serialize responses through orjson.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

_orjson = types.ModuleType("orjson")
_orjson.OPT_NON_STR_KEYS = 1
_orjson.OPT_SERIALIZE_NUMPY = 2
_orjson.dumps = lambda obj, default=None, option=None: json.dumps(obj).encode()  # type: ignore[attr-defined]
_orjson.loads = json.loads  # type: ignore[attr-defined]
sys.modules.setdefault("orjson", _orjson)

from metatracer.api.app import create_app  # noqa: E402
from metatracer.api.webhooks import register_routes as register_webhook_routes  # noqa: E402

ROOT = Path(__file__).resolve().parent


def main() -> None:
    # Webhook routes are attached inside the FastAPI lifespan, so a bare
    # create_app().openapi() omits them. Registering with no session factory
    # matches a booted server's schema and does not open a database.
    app = create_app()
    register_webhook_routes(app)
    schema = app.openapi()
    target = ROOT / "openapi.json"
    target.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"openapi {schema.get('openapi')}")
    print(f"paths {len(schema.get('paths', {}))}")
    print(f"schemas {len(schema.get('components', {}).get('schemas', {}))}")
    print(target)


if __name__ == "__main__":
    main()
