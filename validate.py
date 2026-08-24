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
from collections.abc import Hashable
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

# for each compound type, the extra key that carries its meaning beyond ``type``.
DEFINING_KEYS = {
    "enum": "values",
    "ref": "target",
    "list_ref": "target",
    "list": "item",
}


def validate_field_spec(
    errors: list[str],
    file: str,
    label: str,
    spec: object,
    defined_types: set[str],
    seen: tuple[int, ...] = (),
) -> None:
    """Validate one field spec (a ``{type: ...}`` mapping).

    ``label`` is the ``type.field`` prefix used in diagnostics; ``defined_types``
    is the set of type names defined in the same file, used to resolve ref
    targets.  Applies to specs under both ``key`` and ``fields``, and recurses
    into ``list`` item specs.  ``seen`` holds the ``id()`` of the specs on the
    path to this one; callers do not pass it.
    """
    if not isinstance(spec, dict):
        errors.append(f"{file}: {label}: field spec must be a mapping")
        return
    if id(spec) in seen:
        errors.append(f"{file}: {label}: field spec nests itself")
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
            validate_field_spec(
                errors, file, f"{label}.item", item, defined_types, seen + (id(spec),)
            )


def compare_key_and_field_spec(
    errors: list[str],
    file: str,
    label: str,
    key_spec: object,
    field_spec: object,
    seen: tuple[tuple[int, int], ...] = (),
) -> None:
    """Check that a field declared under both ``key`` and ``fields`` agrees.

    Only the attributes that determine the field's shape are compared: ``type``,
    plus whichever extra key that type requires (``target``, ``values``,
    ``item``).  Metadata such as ``required`` is free to differ — playbooks
    conventionally mark it only under ``fields``.  A ``list``'s two ``item``
    specs are compared by this same rule, so it holds at every depth.  A spec
    pair already on the path is left to ``validate_field_spec`` to report.
    """
    if not isinstance(key_spec, dict) or not isinstance(field_spec, dict):
        return
    pair = (id(key_spec), id(field_spec))
    if pair in seen:
        return

    key_type = key_spec.get("type")
    field_type = field_spec.get("type")
    if key_type != field_type:
        errors.append(
            f"{file}: {label}: 'key' and 'fields' disagree on 'type': "
            f"{key_type!r} vs {field_type!r}"
        )
        return

    attr = DEFINING_KEYS.get(key_type) if isinstance(key_type, str) else None
    if attr is None:
        return
    if key_type == "list":
        compare_key_and_field_spec(
            errors,
            file,
            f"{label}.{attr}",
            key_spec.get(attr),
            field_spec.get(attr),
            seen + (pair,),
        )
        return
    if key_spec.get(attr) != field_spec.get(attr):
        errors.append(
            f"{file}: {label}: 'key' and 'fields' disagree on '{attr}': "
            f"{key_spec.get(attr)!r} vs {field_spec.get(attr)!r}"
        )


def _is_dotted_type_name(name: object) -> bool:
    """True if ``name`` has the ``<namespace>.<type>`` shape ``SPEC.md`` requires."""
    if not isinstance(name, str):
        return False
    segments = name.split(".")
    return len(segments) == 2 and all(segments)


def validate_type(
    errors: list[str],
    file: str,
    type_name: object,
    definition: object,
    defined_types: set[str],
) -> None:
    """Validate a single ``<namespace>.<type>`` definition."""
    if not _is_dotted_type_name(type_name):
        errors.append(f"{file}: {type_name}: type name must be '<namespace>.<type>'")

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
    if key_ok and not key:
        errors.append(f"{file}: {type_name}: 'key' must declare at least one field")

    if fields_ok:
        for field_name, spec in fields.items():
            validate_field_spec(
                errors, file, f"{type_name}.{field_name}", spec, defined_types
            )

    if key_ok:
        for field_name, spec in key.items():
            label = f"{type_name}.{field_name}"
            validate_field_spec(errors, file, label, spec, defined_types)
            if not fields_ok:
                continue
            if field_name not in fields:
                errors.append(f"{file}: {label}: key field not present in 'fields'")
            else:
                compare_key_and_field_spec(
                    errors, file, label, spec, fields[field_name]
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


_MERGE_TAG = "tag:yaml.org,2002:merge"
_VALUE_TAG = "tag:yaml.org,2002:value"


class _DuplicateKeyError(yaml.constructor.ConstructorError):
    """A mapping repeated a key; ``key`` is the offending name."""

    def __init__(self, key: object, node: yaml.Node, key_node: yaml.Node) -> None:
        self.key = key
        super().__init__(
            "while constructing a mapping",
            node.start_mark,
            f"found duplicate key {key!r}",
            key_node.start_mark,
        )


class _StrictLoader(yaml.SafeLoader):
    """A ``SafeLoader`` that rejects duplicate mapping keys.

    PyYAML keeps only the last value when a mapping repeats a key, silently
    dropping the earlier definition — so a playbook with two type definitions
    of the same name, or two identically named fields, would lose one with no
    diagnostic. This loader raises ``_DuplicateKeyError`` at parse time instead.

    Only the keys a mapping writes out itself are compared: a ``<<`` merge
    brings in keys the mapping may then override, which is no repeat.
    """

    def __init__(self, stream: object) -> None:
        super().__init__(stream)
        self._checked: set[yaml.Node] = set()

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict:
        self._reject_duplicate_keys(node, deep)
        return super().construct_mapping(node, deep=deep)

    def _reject_duplicate_keys(self, node: yaml.Node, deep: bool) -> None:
        """Raise if ``node`` repeats a key, recursing into its merge sources."""
        if isinstance(node, yaml.SequenceNode):
            for item in node.value:
                self._reject_duplicate_keys(item, deep)
            return
        if not isinstance(node, yaml.MappingNode) or node in self._checked:
            return
        self._checked.add(node)

        seen: set = set()
        for key_node, value_node in node.value:
            if key_node.tag == _MERGE_TAG:
                self._reject_duplicate_keys(value_node, deep)
                continue
            # ``=`` is only a plain key once ``flatten_mapping`` has retagged it.
            key = (
                key_node.value
                if key_node.tag == _VALUE_TAG
                else self.construct_object(key_node, deep=deep)
            )
            if not isinstance(key, Hashable):
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found unhashable key",
                    key_node.start_mark,
                )
            if key in seen:
                raise _DuplicateKeyError(key, node, key_node)
            seen.add(key)


def validate_file(path: Path) -> list[str]:
    """Load and validate a single playbook file."""
    file = path.name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{file}: cannot read file: {exc}"]
    try:
        doc = yaml.load(text, Loader=_StrictLoader)
        return validate_document(file, doc)
    except _DuplicateKeyError as exc:
        return [f"{file}: duplicate key '{exc.key}'"]
    except yaml.YAMLError as exc:
        return [f"{file}: YAML parse error: {exc}"]
    except RecursionError:
        return [f"{file}: too deeply nested or self-referential to validate"]


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
