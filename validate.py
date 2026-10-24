#!/usr/bin/env python3
"""Validator for alembic schema playbooks.

Loads every ``*.yaml`` playbook in the repo root (or the files named on the
command line) and checks it against the playbook contract documented in
``SPEC.md``.  Prints one ``file: type.field: message`` diagnostic per problem
and exits non-zero if any playbook is invalid.

Depends only on the standard library and PyYAML.
"""

from __future__ import annotations

import math
import re
import sys
from collections.abc import Hashable
from pathlib import Path
from typing import ClassVar

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

# types with no scalar identity form, so alembic rejects them as key fields.
COMPOSITE_TYPES = frozenset({"list", "list_ref"})

# the metadata alembic reads from a field spec, with the value an absent key reads as.
METADATA_DEFAULTS = {
    "required": False,
    "nullable": False,
    "format": None,
    "pattern": None,
    "description": None,
}

# for each compound type, the extra key that carries its meaning beyond ``type``.
DEFINING_KEYS = {
    "enum": "values",
    "ref": "target",
    "list_ref": "target",
    "list": "item",
}

# the ``format`` values alembic accepts.
FORMATS = frozenset({"slug", "ip_address", "cidr", "prefix", "mac", "uuid"})


def validate_field_spec(
    errors: list[str],
    file: str,
    label: str,
    spec: object,
    defined_types: set[str],
    seen: tuple[int, ...] = (),
    is_item: bool = False,
) -> None:
    """Validate one field spec (a ``{type: ...}`` mapping).

    ``label`` is the ``type.field`` prefix used in diagnostics; ``defined_types``
    is the set of type names defined in the same file, used to resolve ref
    targets.  Applies to specs under both ``key`` and ``fields``, and recurses
    into ``list`` item specs, which take no metadata.  ``seen`` holds the
    ``id()`` of the specs on the path to this one; callers do not pass it, nor
    ``is_item``.
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
    if not isinstance(ftype, str):
        errors.append(f"{file}: {label}: 'type' must be a string")
        return
    if ftype not in KNOWN_TYPES:
        errors.append(f"{file}: {label}: unknown type '{ftype}'")
        return

    allowed = {"type"} if is_item else {"type", *METADATA_DEFAULTS}
    if ftype in DEFINING_KEYS:
        allowed.add(DEFINING_KEYS[ftype])
    for key in spec:
        if key not in allowed:
            errors.append(f"{file}: {label}: unknown key '{key}'")
    if not is_item:
        validate_metadata(errors, file, label, spec)

    if ftype == "enum":
        values = spec.get("values")
        if not isinstance(values, list) or not values:
            errors.append(f"{file}: {label}: enum requires a non-empty 'values' list")
        elif not all(isinstance(value, str) for value in values):
            errors.append(f"{file}: {label}: enum values must be strings")
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
                errors,
                file,
                f"{label}.item",
                item,
                defined_types,
                seen + (id(spec),),
                is_item=True,
            )


def validate_metadata(errors: list[str], file: str, label: str, spec: dict) -> None:
    """Check that a field spec's metadata has the types alembic reads it as."""
    for attr in ("required", "nullable"):
        if attr in spec and not isinstance(spec[attr], bool):
            errors.append(f"{file}: {label}: '{attr}' must be a boolean")
    for attr in ("format", "pattern", "description"):
        if attr in spec and not isinstance(spec[attr], str):
            errors.append(f"{file}: {label}: '{attr}' must be a string")
    fmt = spec.get("format")
    if isinstance(fmt, str) and fmt not in FORMATS:
        errors.append(f"{file}: {label}: unknown format '{fmt}'")


def _same_value(a: object, b: object) -> bool:
    """True if ``a == b`` and their types match, at every level of a list or mapping."""
    if a is b:
        return True
    if type(a) is not type(b):
        return False
    if isinstance(a, list):
        return len(a) == len(b) and all(map(_same_value, a, b))
    if isinstance(a, dict):
        a = {(type(k), k): v for k, v in a.items()}
        b = {(type(k), k): v for k, v in b.items()}
        return a.keys() == b.keys() and all(_same_value(v, b[k]) for k, v in a.items())
    return a == b


def compare_key_and_field_spec(
    errors: list[str],
    file: str,
    label: str,
    key_spec: object,
    field_spec: object,
    seen: tuple[tuple[int, int], ...] = (),
) -> bool:
    """Check that a key field's two declarations agree on its type.

    Compares ``type``, plus whichever extra key that type requires (``target``,
    ``values``, ``item``).  A ``list``'s two ``item`` specs are compared by this
    same rule, so it holds at every depth.  Reports the first disagreement and
    returns whether there was one.  A spec pair already on the path is left to
    ``validate_field_spec`` to report.
    """
    if not isinstance(key_spec, dict) or not isinstance(field_spec, dict):
        return False
    pair = (id(key_spec), id(field_spec))
    if pair in seen:
        return False

    key_type = key_spec.get("type")
    field_type = field_spec.get("type")
    if key_type != field_type:
        errors.append(
            f"{file}: {label}: 'key' and 'fields' disagree on 'type': "
            f"{key_type!r} vs {field_type!r}"
        )
        return True

    attr = DEFINING_KEYS.get(key_type) if isinstance(key_type, str) else None
    if attr is None:
        return False
    if key_type == "list":
        return compare_key_and_field_spec(
            errors,
            file,
            f"{label}.{attr}",
            key_spec.get(attr),
            field_spec.get(attr),
            seen + (pair,),
        )
    if not _same_value(key_spec.get(attr), field_spec.get(attr)):
        errors.append(
            f"{file}: {label}: 'key' and 'fields' disagree on '{attr}': "
            f"{key_spec.get(attr)!r} vs {field_spec.get(attr)!r}"
        )
        return True
    return False


def compare_key_and_field_metadata(
    errors: list[str], file: str, label: str, key_spec: object, field_spec: object
) -> None:
    """Check that a key field's two declarations agree on its metadata.

    An absent key counts as its ``METADATA_DEFAULTS`` value, so leaving out
    ``required`` agrees with ``required: false``.  Reports the first disagreement.
    """
    if not isinstance(key_spec, dict) or not isinstance(field_spec, dict):
        return
    for attr, default in METADATA_DEFAULTS.items():
        key_value = key_spec.get(attr, default)
        field_value = field_spec.get(attr, default)
        if not _same_value(key_value, field_value):
            errors.append(
                f"{file}: {label}: 'key' and 'fields' disagree on '{attr}': "
                f"{key_value!r} vs {field_value!r}"
            )
            return


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
    for attr in definition:
        if attr not in ("key", "fields"):
            errors.append(f"{file}: {type_name}: unknown key '{attr}'")

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
            if isinstance(spec, dict):
                ftype = spec.get("type")
                if spec.get("nullable") is True:
                    errors.append(f"{file}: {label}: key field may not be nullable")
                if isinstance(ftype, str) and ftype in COMPOSITE_TYPES:
                    errors.append(f"{file}: {label}: key field may not be a {ftype}")
            if not fields_ok:
                continue
            if field_name not in fields:
                errors.append(f"{file}: {label}: key field not present in 'fields'")
            elif not compare_key_and_field_spec(
                errors, file, label, spec, fields[field_name]
            ):
                compare_key_and_field_metadata(
                    errors, file, label, spec, fields[field_name]
                )


def validate_document(file: str, doc: object) -> list[str]:
    """Validate a parsed playbook document, returning a list of diagnostics."""
    errors: list[str] = []

    if not isinstance(doc, dict):
        errors.append(f"{file}: top-level document must be a mapping")
        return errors

    for key in doc:
        if key != "schema":
            errors.append(f"{file}: unknown key '{key}'")
    schema = doc.get("schema")
    if isinstance(schema, dict):
        for key in schema:
            if key != "types":
                errors.append(f"{file}: schema: unknown key '{key}'")
    types = schema.get("types") if isinstance(schema, dict) else None
    if not isinstance(types, dict):
        errors.append(f"{file}: missing 'schema.types' mapping")
        return errors

    defined_types = set(types.keys())
    for type_name, definition in types.items():
        validate_type(errors, file, type_name, definition, defined_types)

    return errors


_MERGE_TAG = "tag:yaml.org,2002:merge"
_NON_FINITE = r"[-+]?\.(?i:inf|nan)"

# how alembic's yaml reader types a plain scalar; any other plain scalar is a string.
_PLAIN_SCALARS = [
    ("tag:yaml.org,2002:null", r"~|(?i:null)|", ["~", "n", "N", ""]),
    ("tag:yaml.org,2002:bool", r"(?i:true|false)", list("tTfF")),
    (
        "tag:yaml.org,2002:int",
        (
            r"[-+]?(?:0|[1-9][0-9]*(?:_[0-9]+)*|0[xX][0-9a-fA-F]+(?:_[0-9a-fA-F]+)*"
            r"|0[oO][0-7]+(?:_[0-7]+)*|0[bB][01]+(?:_[01]+)*)"
        ),
        list("-+0123456789"),
    ),
    (
        "tag:yaml.org,2002:float",
        r"[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?|" + _NON_FINITE,
        list("-+.0123456789"),
    ),
    (_MERGE_TAG, r"<<", ["<"]),
]

# the ints alembic reads as ints: an i64 or a u64.
_INT_RANGE = range(-(2**63), 2**64)


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


class _RejectedScalarError(yaml.constructor.ConstructorError):
    """A scalar alembic's reader refuses; ``message`` is the diagnostic."""

    def __init__(self, message: str, node: yaml.Node) -> None:
        self.message = message
        super().__init__(None, None, message, node.start_mark)


class _StrictLoader(yaml.SafeLoader):
    """A ``SafeLoader`` that reads scalars as alembic does and rejects duplicate keys.

    PyYAML keeps only the last value when a mapping repeats a key, silently
    dropping the earlier definition — so a playbook with two type definitions
    of the same name, or two identically named fields, would lose one with no
    diagnostic. This loader raises ``_DuplicateKeyError`` at parse time instead.

    Only the keys a mapping writes out itself are compared: a ``<<`` merge
    brings in keys the mapping may then override, which is no repeat.
    """

    yaml_implicit_resolvers: ClassVar[dict] = {}

    def __init__(self, stream: object) -> None:
        super().__init__(stream)
        self._checked: set[yaml.Node] = set()

    def construct_int(self, node: yaml.ScalarNode) -> int | float | str:
        """An int, or past 64 bits a float if written in decimal, else a string."""
        text = self.construct_scalar(node)
        try:
            value = int(text, 0)
        except ValueError:
            raise yaml.constructor.ConstructorError(
                None, None, f"cannot read {text!r} as an int", node.start_mark
            ) from None
        if value in _INT_RANGE:
            return value
        return self.construct_float(node) if text.lstrip("+-").isdigit() else text

    def construct_float(self, node: yaml.ScalarNode) -> float:
        text = self.construct_scalar(node)
        try:
            value = math.inf if re.fullmatch(_NON_FINITE, text) else float(text)
        except ValueError:
            raise yaml.constructor.ConstructorError(
                None, None, f"cannot read {text!r} as a float", node.start_mark
            ) from None
        if not math.isfinite(value):
            raise _RejectedScalarError(f"non-finite float '{text}'", node)
        return value

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
            key = self.construct_object(key_node, deep=deep)
            if key is None:
                raise _RejectedScalarError("mapping key may not be null", key_node)
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


for _tag, _pattern, _first in _PLAIN_SCALARS:
    _StrictLoader.add_implicit_resolver(_tag, re.compile(f"(?:{_pattern})\\Z"), _first)
_StrictLoader.add_constructor("tag:yaml.org,2002:int", _StrictLoader.construct_int)
_StrictLoader.add_constructor("tag:yaml.org,2002:float", _StrictLoader.construct_float)
_StrictLoader.add_constructor(_MERGE_TAG, _StrictLoader.construct_yaml_str)


def validate_file(path: Path) -> list[str]:
    """Load and validate a single playbook file."""
    file = path.name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{file}: cannot read file: {exc}"]
    except UnicodeDecodeError as exc:
        byte = exc.object[exc.start]
        return [f"{file}: not valid UTF-8: byte 0x{byte:02x} at offset {exc.start}"]
    try:
        doc = yaml.load(text, Loader=_StrictLoader)
        return validate_document(file, doc)
    except _DuplicateKeyError as exc:
        return [f"{file}: duplicate key '{exc.key}'"]
    except _RejectedScalarError as exc:
        return [f"{file}: {exc.message}"]
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
