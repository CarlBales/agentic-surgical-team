"""A minimal JSON Schema (2020-12 subset) validator for st's own schemas.

Test-only, so st keeps zero runtime dependencies. Supports exactly what
schema/*.json uses: $ref (relative file and #/$defs/... pointers), type,
properties, required, additionalProperties (boolean), items, enum, const,
pattern, minimum, minItems, minLength, oneOf, anyOf, allOf, not. Any other
keyword is an error, so a schema can't silently use something unchecked.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"
KNOWN = {"$schema", "$id", "title", "description", "$defs", "$ref", "type", "properties",
         "required", "additionalProperties", "items", "enum", "const", "pattern", "minimum",
         "minItems", "minLength", "oneOf", "anyOf", "allOf", "not"}
TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None),
         "number": (int, float), "integer": int}


def _load(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text())


def _type_ok(value: Any, t: str) -> bool:
    if t in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, TYPES[t])


def errors(value: Any, schema: Any, root: dict[str, Any], path: str = "$") -> list[str]:
    if schema is True or schema == {}:
        return []
    unknown = set(schema) - KNOWN
    if unknown:
        raise ValueError(f"schema uses unsupported keywords {sorted(unknown)} at {path}")
    out: list[str] = []
    if "$ref" in schema:
        ref = schema["$ref"]
        file, _, pointer = ref.partition("#")
        doc = _load(file) if file else root
        target: Any = doc
        for part in [p for p in pointer.split("/") if p]:
            target = target[part]
        out += errors(value, target, doc, path)
    if "type" in schema:
        ts = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(value, t) for t in ts):
            return out + [f"{path}: expected {'/'.join(ts)}, got {type(value).__name__}"]
    if "const" in schema and value != schema["const"]:
        out.append(f"{path}: expected {schema['const']!r}, got {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path}: {value!r} not in {schema['enum']}")
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            out.append(f"{path}: {value!r} does not match {schema['pattern']}")
        if len(value) < schema.get("minLength", 0):
            out.append(f"{path}: shorter than {schema['minLength']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and \
            "minimum" in schema and value < schema["minimum"]:
        out.append(f"{path}: {value} < {schema['minimum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            out.append(f"{path}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                out += errors(item, schema["items"], root, f"{path}[{i}]")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                out.append(f"{path}: missing {k!r}")
        for k, v in value.items():
            if k in props:
                out += errors(v, props[k], root, f"{path}.{k}")
            elif schema.get("additionalProperties") is False:
                out.append(f"{path}: unexpected field {k!r}")
    for sub in schema.get("allOf", []):
        out += errors(value, sub, root, path)
    if "anyOf" in schema and not any(not errors(value, s, root, path) for s in schema["anyOf"]):
        out.append(f"{path}: matches none of anyOf")
    if "oneOf" in schema:
        n = sum(1 for s in schema["oneOf"] if not errors(value, s, root, path))
        if n != 1:
            out.append(f"{path}: matches {n} of oneOf, expected exactly 1")
    if "not" in schema and not errors(value, schema["not"], root, path):
        out.append(f"{path}: matches a forbidden schema")
    return out


def validate(value: Any, schema_name: str) -> list[str]:
    root = _load(schema_name)
    return errors(value, root, root)
