"""Load the JSON Schemas stored under templates/ and report structural errors."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from lib.util import repo_root


@lru_cache(maxsize=32)
def load_schema(name: str, root: str | None = None) -> dict:
    path = Path(root) / "templates" / name if root else repo_root() / "templates" / name
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        import json

        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a schema object")
    return data


def check_schema_document(schema: dict) -> list[str]:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return [str(exc)]
    return []


def instance_errors(instance, schema: dict) -> list[str]:
    validator = Draft202012Validator(schema)
    errors = []
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path)):
        loc = "/".join(str(part) for part in error.absolute_path) or "(root)"
        errors.append(f"{loc}: {error.message}")
    return errors
