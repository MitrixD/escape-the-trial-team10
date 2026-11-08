import json
from datetime import date
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "verdict_agent" / "schema.json"

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "null": lambda v: v is None,
    "boolean": lambda v: isinstance(v, bool),
}


def load_schema():
    return json.loads(SCHEMA_PATH.read_text())


def _is_date(v):
    try:
        date.fromisoformat(v)
    except ValueError:
        return False
    return True


def errors(value, schema, path="$"):
    found = []
    types = schema.get("type")
    if types is not None:
        types = [types] if isinstance(types, str) else types
        if not any(_TYPES[t](value) for t in types):
            return [f"{path}: expected {types}, got {value!r}"]
    if "enum" in schema and value not in schema["enum"]:
        found.append(f"{path}: {value!r} not in {schema['enum']}")
    if "minimum" in schema and _TYPES["number"](value) and value < schema["minimum"]:
        found.append(f"{path}: {value} below {schema['minimum']}")
    if "maximum" in schema and _TYPES["number"](value) and value > schema["maximum"]:
        found.append(f"{path}: {value} above {schema['maximum']}")
    if schema.get("format") == "date" and isinstance(value, str) and not _is_date(value):
        found.append(f"{path}: {value!r} is not a date")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                found.append(f"{path}: missing {key}")
        if schema.get("additionalProperties") is False:
            found.extend(f"{path}: unexpected {key}" for key in value if key not in props)
        for key, sub in props.items():
            if key in value:
                found.extend(errors(value[key], sub, f"{path}.{key}"))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            found.append(f"{path}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                found.extend(errors(item, schema["items"], f"{path}[{i}]"))
    for sub in schema.get("allOf", []):
        if "if" in sub:
            if not errors(value, sub["if"], path):
                found.extend(errors(value, sub.get("then", {}), path))
        else:
            found.extend(errors(value, sub, path))
    return found


def assert_valid(value):
    problems = errors(value, load_schema())
    assert not problems, problems
