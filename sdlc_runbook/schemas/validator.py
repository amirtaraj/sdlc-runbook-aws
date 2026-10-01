"""Minimal validator for the subset of JSON Schema the runbook uses (object, array, string, boolean, enum)."""
from ..exceptions import SchemaError


def validate(value, schema: dict, path: str = "$") -> None:
    kind = schema["type"]
    if kind == "string":
        if not isinstance(value, str):
            raise SchemaError(f"{path}: expected string")
        if "enum" in schema and value not in schema["enum"]:
            raise SchemaError(f"{path}: expected one of {schema['enum']}")
    elif kind == "boolean":
        if not isinstance(value, bool):
            raise SchemaError(f"{path}: expected boolean")
    elif kind == "array":
        if not isinstance(value, list):
            raise SchemaError(f"{path}: expected array")
        for i, item in enumerate(value):
            validate(item, schema["items"], f"{path}[{i}]")
    elif kind == "object":
        if not isinstance(value, dict):
            raise SchemaError(f"{path}: expected object")
        missing = set(schema["required"]) - value.keys()
        extra = value.keys() - schema["properties"].keys()
        if missing:
            raise SchemaError(f"{path}: missing keys {sorted(missing)}")
        if extra:
            raise SchemaError(f"{path}: unexpected keys {sorted(extra)}")
        for key, sub in schema["properties"].items():
            validate(value[key], sub, f"{path}.{key}")
    else:
        raise SchemaError(f"{path}: unsupported schema type {kind!r}")
