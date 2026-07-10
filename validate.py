#!/usr/bin/env python3
"""Validator for alembic schema playbooks.

Loads every ``*.yaml`` playbook in the repo root (or the files named on the
command line) and checks it against the playbook contract documented in
``SPEC.md``.  Prints one ``file: type.field: message`` diagnostic per problem
and exits non-zero if any playbook is invalid.

Depends only on the standard library and PyYAML.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

# Field ``type`` values understood by the format.
SIMPLE_TYPES = frozenset(
    {
        "string",
        "text",
        "bool",
        "int",
        "float",
        "ip_address",
        "mac",
        "prefix",
        "slug",
    }
)
REF_TYPES = frozenset({"ref", "list_ref"})
KNOWN_TYPES = SIMPLE_TYPES | REF_TYPES | {"enum", "list"}


def validate_field_spec(
    errors: list[str],
    file: str,
    label: str,
    spec: object,
    defined_types: set[str],
) -> None:
    """Validate one field spec (a ``{type: ...}`` mapping).

    ``label`` is the ``type.field`` prefix used in diagnostics; ``defined_types``
    is the set of type names defined in the same file, used to resolve ref
    targets.  Applies to specs under both ``key`` and ``fields``, and recurses
    into ``list`` item specs.
    """
    if not isinstance(spec, dict):
        errors.append(f"{file}: {label}: field spec must be a mapping")
        return

    ftype = spec.get("type")
    if ftype is None:
        errors.append(f"{file}: {label}: missing 'type'")
        return
    if ftype not in KNOWN_TYPES:
        errors.append(f"{file}: {label}: unknown type '{ftype}'")
        return

    if ftype == "enum":
        values = spec.get("values")
        if not isinstance(values, list) or not values:
            errors.append(f"{file}: {label}: enum requires a non-empty 'values' list")
    elif ftype in REF_TYPES:
        target = spec.get("target")
        if not isinstance(target, str) or not target:
            errors.append(f"{file}: {label}: {ftype} requires a 'target'")
        elif target not in defined_types:
            errors.append(
                f"{file}: {label}: {ftype} target '{target}' "
                "is not defined in this file"
            )
    elif ftype == "list":
        item = spec.get("item")
        if not isinstance(item, dict) or "type" not in item:
            errors.append(f"{file}: {label}: list requires 'item.type'")
        else:
            validate_field_spec(errors, file, f"{label}.item", item, defined_types)


def validate_type(
    errors: list[str],
    file: str,
    type_name: str,
    definition: object,
    defined_types: set[str],
) -> None:
    """Validate a single ``<namespace>.<type>`` definition."""
    if not isinstance(definition, dict):
        errors.append(f"{file}: {type_name}: type definition must be a mapping")
        return

    key = definition.get("key")
    fields = definition.get("fields")
    key_ok = isinstance(key, dict)
    fields_ok = isinstance(fields, dict)
    if not key_ok:
        errors.append(f"{file}: {type_name}: missing 'key' mapping")
    if not fields_ok:
        errors.append(f"{file}: {type_name}: missing 'fields' mapping")

    if fields_ok:
        for field_name, spec in fields.items():
            validate_field_spec(
                errors, file, f"{type_name}.{field_name}", spec, defined_types
            )

    if key_ok:
        for field_name, spec in key.items():
            validate_field_spec(
                errors, file, f"{type_name}.{field_name}", spec, defined_types
            )
            if fields_ok and field_name not in fields:
                errors.append(
                    f"{file}: {type_name}.{field_name}: "
                    "key field not present in 'fields'"
                )


def validate_document(file: str, doc: object) -> list[str]:
    """Validate a parsed playbook document, returning a list of diagnostics."""
    errors: list[str] = []

    if not isinstance(doc, dict):
        errors.append(f"{file}: top-level document must be a mapping")
        return errors

    schema = doc.get("schema")
    types = schema.get("types") if isinstance(schema, dict) else None
    if not isinstance(types, dict):
        errors.append(f"{file}: missing 'schema.types' mapping")
        return errors

    defined_types = set(types.keys())
    for type_name, definition in types.items():
        validate_type(errors, file, type_name, definition, defined_types)

    return errors


def validate_file(path: Path) -> list[str]:
    """Load and validate a single playbook file."""
    file = path.name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{file}: cannot read file: {exc}"]
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return [f"{file}: YAML parse error: {exc}"]
    return validate_document(file, doc)


def main(argv: list[str]) -> int:
    if argv:
        paths = [Path(a) for a in argv]
    else:
        paths = sorted(Path(__file__).resolve().parent.glob("*.yaml"))

    if not paths:
        print("no playbooks found to validate")
        return 0

    errors: list[str] = []
    for path in paths:
        errors.extend(validate_file(path))

    for message in errors:
        print(message)

    if errors:
        print(f"\n{len(errors)} problem(s) found in {len(paths)} playbook(s)")
        return 1
    print(f"all {len(paths)} playbook(s) valid")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
