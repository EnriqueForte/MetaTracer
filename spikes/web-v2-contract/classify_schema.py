"""Classify OpenAPI operations for the Web V2 type spike. Prints a text report."""

from __future__ import annotations

import json
from pathlib import Path

schema = json.loads(Path(__file__).with_name("openapi.json").read_text(encoding="utf-8"))
components = schema["components"]["schemas"]


def resolve(node: dict | None, seen: set[str] | None = None) -> dict:
    if not isinstance(node, dict):
        return {}
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        if seen and name in seen:
            return {"$circular": name}
        seen = set(seen or ())
        seen.add(name)
        return resolve(components.get(name, {}), seen)
    return node


def loose(node: dict | None) -> str | None:
    """Return a short reason if the node is too wide to be a safe client type."""
    resolved = resolve(node)
    if not resolved:
        return "missing"
    if resolved.get("$circular"):
        return None
    if "anyOf" in resolved or "oneOf" in resolved:
        parts = resolved.get("anyOf") or resolved.get("oneOf")
        reasons = [loose(part) for part in parts]
        if any(reasons):
            return "union:" + ",".join(r or "ok" for r in reasons)
        return None
    schema_type = resolved.get("type")
    props = resolved.get("properties") or {}
    additional = resolved.get("additionalProperties")
    if schema_type == "object" and not props and additional in (True, {}):
        return "free-object"
    if schema_type == "object" and not props and additional is None and "allOf" not in resolved:
        return "empty-object"
    if additional is True:
        return "additional-free"
    if isinstance(additional, dict) and additional.get("type") is None and "$ref" not in additional:
        # additionalProperties: {} means any JSON value
        if additional == {} or additional.get("additionalProperties") is True:
            return "additional-any"
    wide_fields = []
    for key, field in props.items():
        field_resolved = resolve(field)
        if field_resolved.get("type") == "object" and not field_resolved.get("properties"):
            add = field_resolved.get("additionalProperties")
            if add in (True, {}) or (isinstance(add, dict) and not add.get("type") and "$ref" not in add and "properties" not in add):
                wide_fields.append(key)
            elif add is None and "anyOf" not in field_resolved and "allOf" not in field_resolved:
                wide_fields.append(key + ":empty")
        elif field_resolved.get("type") == "array":
            items = field_resolved.get("items") or {}
            item_reason = loose(items)
            if item_reason:
                wide_fields.append(f"{key}[]:{item_reason}")
    if wide_fields:
        return "fields:" + ",".join(wide_fields)
    return None


lines: list[str] = []
ops = 0
for path, methods in schema["paths"].items():
    for method, op in methods.items():
        if method.startswith("x-") or method == "parameters":
            continue
        ops += 1
        responses = op.get("responses") or {}
        bits = []
        for code, resp in responses.items():
            content = (resp or {}).get("content") or {}
            if not content:
                bits.append(f"{code}:empty")
                continue
            for ctype, media in content.items():
                reason = loose(media.get("schema"))
                ref = (media.get("schema") or {}).get("$ref", "")
                label = ref.rsplit("/", 1)[-1] or ctype
                bits.append(f"{code}:{label}" + (f" LOOSE({reason})" if reason else ""))
        body = op.get("requestBody")
        body_bit = ""
        if body:
            content = body.get("content") or {}
            for ctype, media in content.items():
                reason = loose(media.get("schema"))
                ref = (media.get("schema") or {}).get("$ref", "")
                label = ref.rsplit("/", 1)[-1] or ctype
                body_bit = f" body={label}" + (f" LOOSE({reason})" if reason else "")
                if ctype != "application/json":
                    body_bit += f" ctype={ctype}"
        lines.append(f"{method.upper():6} {path}{body_bit} -> {', '.join(bits) or 'NO_RESPONSE'}")

print(f"operations {ops}")
print("\n".join(lines))
print("\n-- component looseness --")
for name, node in components.items():
    reason = loose(node)
    if reason:
        print(f"{name}: {reason}")
