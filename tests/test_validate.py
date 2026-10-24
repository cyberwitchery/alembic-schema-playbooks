import sys
from pathlib import Path

import pytest
import yaml

import validate

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PLAYBOOKS = sorted(REPO_ROOT.glob("*.yaml"))


VALID_CASES = [
    "minimal.yaml",
    "shared_anchor.yaml",
    "merge_override.yaml",
]


@pytest.mark.parametrize("filename", VALID_CASES)
def test_valid_fixture_passes(filename):
    assert validate.validate_file(FIXTURES / "valid" / filename) == []


@pytest.mark.parametrize("playbook", PLAYBOOKS, ids=lambda p: p.name)
def test_real_playbooks_pass(playbook):
    # the shipped playbooks must always validate cleanly, so CI stays green
    assert validate.validate_file(playbook) == []


def test_there_are_real_playbooks_to_check():
    # guard against the parametrized test silently collecting nothing
    assert len(PLAYBOOKS) >= 7


# one fixture per rule: (filename, expected diagnostic substring)
INVALID_CASES = [
    ("missing_schema_types.yaml", "missing 'schema.types' mapping"),
    ("missing_key.yaml", "missing 'key' mapping"),
    ("missing_fields.yaml", "missing 'fields' mapping"),
    ("unknown_type.yaml", "unknown type 'uuid'"),
    ("enum_missing_values.yaml", "enum requires a non-empty 'values' list"),
    ("ref_missing_target.yaml", "ref requires a 'target'"),
    ("list_ref_missing_target.yaml", "list_ref requires a 'target'"),
    ("list_missing_item.yaml", "list requires 'item.type'"),
    ("dangling_ref.yaml", "target 'net.ghost' is not defined in this file"),
    ("key_not_in_fields.yaml", "key field not present in 'fields'"),
    ("duplicate_type.yaml", "duplicate key 'net.thing'"),
    ("duplicate_field.yaml", "duplicate key 'name'"),
    ("merge_duplicate_field.yaml", "duplicate key 'name'"),
    ("key_fields_disagree.yaml", "'key' and 'fields' disagree on 'type'"),
    ("empty_key.yaml", "'key' must declare at least one field"),
    ("undotted_type_name.yaml", "type name must be '<namespace>.<type>'"),
    ("bad_yaml.yaml", "YAML parse error"),
    ("self_nesting_item.yaml", "field spec nests itself"),
    ("nullable_key.yaml", "key field may not be nullable"),
    ("list_ref_key.yaml", "key field may not be a list_ref"),
]


@pytest.mark.parametrize(
    "filename,expected", INVALID_CASES, ids=[c[0] for c in INVALID_CASES]
)
def test_invalid_fixture_reports_its_rule(filename, expected):
    errors = validate.validate_file(FIXTURES / "invalid" / filename)
    # each fixture isolates exactly one rule
    assert len(errors) == 1, errors
    assert expected in errors[0]


def test_enum_empty_values_is_rejected(tmp_path):
    playbook = tmp_path / "e.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {x: {type: string}}\n"
        "      fields: {x: {type: string}, s: {type: enum, values: []}}\n"
    )
    assert validate.validate_file(playbook) == [
        "e.yaml: a.b.s: enum requires a non-empty 'values' list"
    ]


@pytest.mark.parametrize("ftype", ["[string]", "{a: b}"])
def test_non_string_type_is_rejected(tmp_path, ftype):
    playbook = tmp_path / "t.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {x: {type: string}}\n"
        "      fields: {x: {type: string}, s: {type: " + ftype + "}}\n"
    )
    assert validate.validate_file(playbook) == [
        "t.yaml: a.b.s: 'type' must be a string"
    ]


def test_list_item_type_is_validated(tmp_path):
    playbook = tmp_path / "l.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {x: {type: string}}\n"
        "      fields: {x: {type: string}, l: {type: list, item: {type: uuid}}}\n"
    )
    assert validate.validate_file(playbook) == [
        "l.yaml: a.b.l.item: unknown type 'uuid'"
    ]


def test_key_field_specs_are_validated(tmp_path):
    # a dangling target inside a 'key' entry is reported, same as under 'fields'
    playbook = tmp_path / "k.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {r: {type: ref, target: a.missing}}\n"
        "      fields: {r: {type: ref, target: a.missing}}\n"
    )
    errors = validate.validate_file(playbook)
    assert any(
        "a.b.r: ref target 'a.missing' is not defined in this file" in e for e in errors
    )


def test_key_and_fields_type_disagreement_is_rejected(tmp_path):
    playbook = tmp_path / "d.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {x: {type: int}}\n"
        "      fields: {x: {type: string, required: true}}\n"
    )
    assert validate.validate_file(playbook) == [
        "d.yaml: a.b.x: 'key' and 'fields' disagree on 'type': 'int' vs 'string'"
    ]


def test_key_and_fields_target_disagreement_is_rejected(tmp_path):
    # the types agree; only the ref target differs
    playbook = tmp_path / "t.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {r: {type: ref, target: a.b}}\n"
        "      fields: {r: {type: ref, target: a.c}}\n"
        "    a.c:\n"
        "      key: {n: {type: string}}\n"
        "      fields: {n: {type: string}}\n"
    )
    assert validate.validate_file(playbook) == [
        "t.yaml: a.b.r: 'key' and 'fields' disagree on 'target': 'a.b' vs 'a.c'"
    ]


# (id, key values, fields values, the two as reported, or None if they agree)
ENUM_VALUES_CASES = [
    ("int vs bool", "[1, 0]", "[true, false]", "[1, 0] vs [True, False]"),
    ("int vs float", "[1, 2]", "[1.0, 2.0]", "[1, 2] vs [1.0, 2.0]"),
    ("mapping value", "[{a: 1}]", "[{a: true}]", "[{'a': 1}] vs [{'a': True}]"),
    ("mapping key", "[{1: a}]", "[{true: a}]", "[{1: 'a'}] vs [{True: 'a'}]"),
    ("same type, fewer values", "[one, two]", "[one]", "['one', 'two'] vs ['one']"),
]


@pytest.mark.parametrize(
    "key_values,field_values,shown",
    [c[1:] for c in ENUM_VALUES_CASES],
    ids=[c[0] for c in ENUM_VALUES_CASES],
)
def test_key_and_fields_enum_values_are_compared_by_type(
    tmp_path, key_values, field_values, shown
):
    playbook = tmp_path / "v.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        f"      key: {{x: {{type: enum, values: {key_values}}}}}\n"
        f"      fields: {{x: {{type: enum, values: {field_values}}}}}\n"
    )
    disagreement = "v.yaml: a.b.x: 'key' and 'fields' disagree on 'values': "
    expected = [] if shown is None else [disagreement + shown]
    errors = validate.validate_file(playbook)
    assert [e for e in errors if "disagree" in e] == expected


# (id, key extras, fields extras, the two as reported, or None if they agree)
METADATA_CASES = [
    (
        "required, first of two",
        "",
        ", required: true, description: d",
        "'required': False vs True",
    ),
    ("absent is false", "", ", required: false", None),
    ("nullable", "", ", nullable: true", "'nullable': False vs True"),
    ("format", ", format: slug", "", "'format': 'slug' vs None"),
    ("pattern", ", pattern: a", ", pattern: b", "'pattern': 'a' vs 'b'"),
    ("description", "", ", description: d", "'description': None vs 'd'"),
    ("plain and quoted spelling", ", description: yes", ", description: 'yes'", None),
]


@pytest.mark.parametrize(
    "key_extra,field_extra,shown",
    [c[1:] for c in METADATA_CASES],
    ids=[c[0] for c in METADATA_CASES],
)
def test_key_and_fields_must_agree_on_metadata(tmp_path, key_extra, field_extra, shown):
    playbook = tmp_path / "m.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        f"      key: {{x: {{type: enum, values: [one, two]{key_extra}}}}}\n"
        f"      fields: {{x: {{type: enum, values: [one, two]{field_extra}}}}}\n"
    )
    disagreement = "m.yaml: a.b.x: 'key' and 'fields' disagree on "
    expected = [] if shown is None else [disagreement + shown]
    assert validate.validate_file(playbook) == expected


def test_key_and_fields_list_item_type_disagreement_is_rejected(tmp_path):
    playbook = tmp_path / "n.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {t: {type: list, item: {type: string}}}\n"
        "      fields: {t: {type: list, item: {type: int}}}\n"
    )
    assert validate.validate_file(playbook) == [
        "n.yaml: a.b.t: key field may not be a list",
        "n.yaml: a.b.t.item: 'key' and 'fields' disagree on 'type': 'string' vs 'int'",
    ]


def test_key_and_fields_nested_list_item_is_compared_at_depth(tmp_path):
    playbook = tmp_path / "z.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {t: {type: list, item: {type: list, item: "
        "{type: enum, values: [one]}}}}\n"
        "      fields: {t: {type: list, item: {type: list, item: "
        "{type: enum, values: [two]}}}}\n"
    )
    expected = (
        "z.yaml: a.b.t.item.item: 'key' and 'fields' disagree on 'values': "
        "['one'] vs ['two']"
    )
    assert validate.validate_file(playbook) == [
        "z.yaml: a.b.t: key field may not be a list",
        expected,
    ]


# (id, spec of field 's', the diagnostics it gets)
FIELD_SPEC_CASES = [
    (
        "unknown key",
        "{type: string, requried: true}",
        ["a.b.s: unknown key 'requried'"],
    ),
    (
        "another type's extra key",
        "{type: enum, values: [a], target: a.b}",
        ["a.b.s: unknown key 'target'"],
    ),
    (
        "metadata in a list item",
        "{type: list, item: {type: string, required: yes}}",
        ["a.b.s.item: unknown key 'required'"],
    ),
    ("a list item's extra key", "{type: list, item: {type: enum, values: [a]}}", []),
    (
        "valid metadata",
        (
            "{type: string, required: TRUE, nullable: false, format: cidr, "
            "pattern: '^a', description: d}"
        ),
        [],
    ),
    (
        "boolean metadata",
        "{type: string, required: yes, nullable: no}",
        ["a.b.s: 'required' must be a boolean", "a.b.s: 'nullable' must be a boolean"],
    ),
    (
        "string metadata",
        "{type: string, format: 1, pattern: [a], description: ~}",
        [
            "a.b.s: 'format' must be a string",
            "a.b.s: 'pattern' must be a string",
            "a.b.s: 'description' must be a string",
        ],
    ),
    ("format", "{type: string, format: bogus}", ["a.b.s: unknown format 'bogus'"]),
    (
        "enum values",
        "{type: enum, values: [a, 1e3]}",
        ["a.b.s: enum values must be strings"],
    ),
    (
        "non-finite float",
        "{type: enum, values: [a, -.Inf]}",
        ["non-finite float '-.Inf'"],
    ),
    ("null key", "{type: string, ~: a}", ["mapping key may not be null"]),
]


@pytest.mark.parametrize(
    "spec,shown",
    [c[1:] for c in FIELD_SPEC_CASES],
    ids=[c[0] for c in FIELD_SPEC_CASES],
)
def test_field_spec_is_read_as_alembic_reads_it(tmp_path, spec, shown):
    playbook = tmp_path / "f.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {x: {type: string}}\n"
        f"      fields: {{x: {{type: string}}, s: {spec}}}\n"
    )
    assert validate.validate_file(playbook) == [f"f.yaml: {line}" for line in shown]


@pytest.mark.parametrize(
    "scalar,problem",
    [
        ("!!int 017", "cannot read '017' as an int"),
        ("!!float x", "cannot read 'x' as a float"),
    ],
)
def test_a_tagged_scalar_that_is_no_number_is_a_parse_error(tmp_path, scalar, problem):
    playbook = tmp_path / "t.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {x: {type: string}}\n"
        f"      fields: {{x: {{type: string, description: {scalar}}}}}\n"
    )
    errors = validate.validate_file(playbook)
    assert len(errors) == 1, errors
    assert errors[0].startswith(f"t.yaml: YAML parse error: {problem}")


# (id, text after a valid playbook, the diagnostic)
UNKNOWN_KEY_CASES = [
    ("type definition", "      description: x\n", "a.b: unknown key 'description'"),
    ("schema", "  version: 1\n", "schema: unknown key 'version'"),
    ("top level", "objects: []\n", "unknown key 'objects'"),
]


@pytest.mark.parametrize(
    "tail,shown",
    [c[1:] for c in UNKNOWN_KEY_CASES],
    ids=[c[0] for c in UNKNOWN_KEY_CASES],
)
def test_unknown_keys_are_rejected_at_every_level(tmp_path, tail, shown):
    playbook = tmp_path / "u.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {x: {type: string}}\n"
        "      fields: {x: {type: string}}\n" + tail
    )
    assert validate.validate_file(playbook) == [f"u.yaml: {shown}"]


def test_malformed_list_item_is_reported_once(tmp_path):
    playbook = tmp_path / "o.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {t: {type: list, item: {type: string}}}\n"
        "      fields: {t: {type: list}}\n"
    )
    assert validate.validate_file(playbook) == [
        "o.yaml: a.b.t: list requires 'item.type'",
        "o.yaml: a.b.t: key field may not be a list",
    ]


def test_self_nesting_key_and_fields_specs_are_reported_not_crashed(tmp_path):
    # the spec is checked once under 'fields' and once under 'key'
    playbook = tmp_path / "s.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key:\n        n: &loop\n"
        "          type: list\n          item: *loop\n"
        "      fields:\n        n: *loop\n"
    )
    assert validate.validate_file(playbook) == [
        "s.yaml: a.b.n.item: field spec nests itself",
        "s.yaml: a.b.n.item: field spec nests itself",
        "s.yaml: a.b.n: key field may not be a list",
    ]


def test_self_nesting_is_reported_at_the_depth_the_cycle_closes(tmp_path):
    playbook = tmp_path / "c.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {x: {type: string}}\n"
        "      fields:\n        x: {type: string}\n"
        "        t: &a\n          type: list\n"
        "          item:\n            type: list\n            item: *a\n"
    )
    assert validate.validate_file(playbook) == [
        "c.yaml: a.b.t.item.item: field spec nests itself"
    ]


MERGE_CASES = [
    ("override", "b: &b {name: one, extra: 1}\nd:\n  <<: *b\n  name: two\n"),
    ("sequence", "a: &a {name: one}\nb: &b {name: two, x: 1}\nd:\n  <<: [*a, *b]\n"),
    ("repeated merge key", "a: &a {p: 1}\nb: &b {q: 2}\nd:\n  <<: *a\n  <<: *b\n"),
    ("chained", "a: &a {name: one}\nb: &b\n  <<: *a\n  name: two\nd:\n  <<: *b\n"),
]


@pytest.mark.parametrize(
    "text", [c[1] for c in MERGE_CASES], ids=[c[0] for c in MERGE_CASES]
)
def test_merge_keys_load_as_pyyaml_defines(text):
    assert yaml.load(text, Loader=validate._StrictLoader) == yaml.safe_load(text)


def test_an_explicit_key_wins_over_a_merged_one():
    text = (
        "a: &a {name: one, x: 1}\nb: &b {name: two, y: 2}\nd:\n  <<: [*a, *b]\n  y: 9\n"
    )
    assert yaml.load(text, Loader=validate._StrictLoader) == {
        "a": {"name": "one", "x": 1},
        "b": {"name": "two", "y": 2},
        "d": {"name": "one", "x": 1, "y": 9},
    }


def test_the_overriding_field_spec_is_the_one_validated(tmp_path):
    playbook = tmp_path / "v.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {x: {type: string}}\n"
        "      fields: &common {x: {type: string}}\n"
        "    a.c:\n"
        "      key: {k: {type: string}}\n"
        "      fields:\n        <<: *common\n"
        "        k: {type: string}\n        x: {type: uuid}\n"
    )
    assert validate.validate_file(playbook) == ["v.yaml: a.c.x: unknown type 'uuid'"]


def test_a_repeat_alongside_a_merge_is_still_a_duplicate(tmp_path):
    playbook = tmp_path / "r.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {x: {type: string}}\n"
        "      fields: &common {x: {type: string}}\n"
        "    a.c:\n"
        "      key: {x: {type: text}}\n"
        "      fields:\n        <<: *common\n"
        "        x: {type: text}\n        x: {type: int}\n"
    )
    assert validate.validate_file(playbook) == ["r.yaml: duplicate key 'x'"]


def test_a_repeat_inside_a_merged_mapping_is_still_a_duplicate(tmp_path):
    playbook = tmp_path / "s.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {x: {type: string}}\n"
        "      fields: &common\n"
        "        x: {type: string}\n        x: {type: text}\n"
        "    a.c:\n"
        "      key: {x: {type: string}}\n"
        "      fields:\n        <<: *common\n"
    )
    assert validate.validate_file(playbook) == ["s.yaml: duplicate key 'x'"]


def test_a_repeat_inside_an_inline_merge_source_is_still_a_duplicate(tmp_path):
    # the source is never a value of its own, so only the merge reaches it
    playbook = tmp_path / "i.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {x: {type: string}}\n"
        "      fields:\n"
        "        <<: {x: {type: string}, x: {type: text}}\n"
    )
    assert validate.validate_file(playbook) == ["i.yaml: duplicate key 'x'"]


def test_a_merge_of_something_other_than_a_mapping_is_a_parse_error(tmp_path):
    playbook = tmp_path / "b.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {x: {type: string}}\n"
        "      fields:\n        <<: 3\n"
    )
    errors = validate.validate_file(playbook)
    assert len(errors) == 1, errors
    assert errors[0].startswith("b.yaml: YAML parse error:")
    assert "expected a mapping or list of mappings for merging" in errors[0]


# (id, a flow sequence of plain scalars, the values alembic's reader gives them)
SCALAR_CASES = [
    (
        "yaml 1.1 booleans",
        "[yes, no, on, off, y, n]",
        ["yes", "no", "on", "off", "y", "n"],
    ),
    ("true and false in any case", "[true, False, TRUE]", [True, False, True]),
    ("null in any case", "[~, null, NULL]", [None, None, None]),
    ("dates and sexagesimals", "[2026-10-24, 1:20]", ["2026-10-24", "1:20"]),
    ("floats", "[1e3, .5, 1., 017]", [1000.0, 0.5, 1.0, 17.0]),
    ("ints", "[+1, -0, 1_000, 0x1F, 0o17, 0O17, 0b1]", [1, 0, 1000, 31, 15, 15, 1]),
    ("not quite numbers", "[0xGG, 1_0.5, 0x_1F, 1e]", ["0xGG", "1_0.5", "0x_1F", "1e"]),
    (
        "past 64 bits",
        "[18446744073709551616, 0x10000000000000000]",
        [2.0**64, "0x10000000000000000"],
    ),
    ("merge and value keys as values", "[<<, =]", ["<<", "="]),
]


@pytest.mark.parametrize(
    "text,expected",
    [c[1:] for c in SCALAR_CASES],
    ids=[c[0] for c in SCALAR_CASES],
)
def test_plain_scalars_load_as_alembic_reads_them(text, expected):
    loaded = yaml.load(f"v: {text}\n", Loader=validate._StrictLoader)["v"]
    assert [(type(v), v) for v in loaded] == [(type(v), v) for v in expected]


def test_a_yaml_value_key_loads_as_the_string_key():
    text = "d:\n  =: 1\n  b: 2\n"
    assert yaml.load(text, Loader=validate._StrictLoader) == {"d": {"=": 1, "b": 2}}


def _deeply_nested_playbook(path):
    # one nesting level costs at least one frame, so this always overflows
    spec = "{type: string}"
    for _ in range(sys.getrecursionlimit()):
        spec = f"{{type: list, item: {spec}}}"
    path.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {x: {type: string}}\n"
        f"      fields: {{x: {{type: string}}, t: {spec}}}\n"
    )
    return path


def test_excessive_nesting_is_reported_not_crashed(tmp_path):
    playbook = _deeply_nested_playbook(tmp_path / "d.yaml")
    assert validate.validate_file(playbook) == [
        "d.yaml: too deeply nested or self-referential to validate"
    ]


def test_a_bad_playbook_does_not_stop_the_others(tmp_path, capsys):
    bad = _deeply_nested_playbook(tmp_path / "d.yaml")
    valid = FIXTURES / "valid" / "minimal.yaml"
    nesting = FIXTURES / "invalid" / "self_nesting_item.yaml"
    assert validate.main([str(bad), str(nesting), str(valid)]) == 1
    out = capsys.readouterr().out
    assert "2 problem(s) found in 3 playbook(s)" in out


def test_self_referential_enum_values_are_reported_not_crashed():
    # the cycle closes in the 'key'/'fields' comparison, not in the loader
    playbook = FIXTURES / "invalid" / "cyclic_enum_values.yaml"
    assert validate.validate_file(playbook) == [
        "cyclic_enum_values.yaml: too deeply nested or self-referential to validate"
    ]


def test_a_self_referential_playbook_does_not_stop_the_others(capsys):
    cyclic = FIXTURES / "invalid" / "cyclic_enum_values.yaml"
    later = FIXTURES / "invalid" / "unknown_type.yaml"
    assert validate.main([str(cyclic), str(later)]) == 1
    out = capsys.readouterr().out
    assert (
        "cyclic_enum_values.yaml: too deeply nested or self-referential to validate"
        in out
    )
    assert "unknown_type.yaml: net.thing.oid: unknown type 'uuid'" in out


def test_a_non_utf8_byte_is_reported_at_its_byte_offset(tmp_path):
    data = (
        b"schema:\n  types:\n    a.b:\n"
        b"      key: {x: {type: string}}\n"
        b"      fields: {x: {type: string, description: na\xc3\xafve caf\xe9}}\n"
    )
    playbook = tmp_path / "u.yaml"
    playbook.write_bytes(data)
    offset = data.index(b"\xe9")
    assert validate.validate_file(playbook) == [
        f"u.yaml: not valid UTF-8: byte 0xe9 at offset {offset}"
    ]


def test_a_utf16_playbook_is_rejected_as_not_utf8(tmp_path):
    text = (
        "\ufeffschema:\n  types:\n    a.b:\n"
        "      key: {x: {type: string}}\n"
        "      fields: {x: {type: string}}\n"
    )
    playbook = tmp_path / "w.yaml"
    playbook.write_bytes(text.encode("utf-16-le"))
    assert validate.validate_file(playbook) == [
        "w.yaml: not valid UTF-8: byte 0xff at offset 0"
    ]


def test_a_non_utf8_playbook_does_not_stop_the_others(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_bytes(b'schema: {types: {}, description: "caf\xe9"}\n')
    later = FIXTURES / "invalid" / "unknown_type.yaml"
    assert validate.main([str(bad), str(later)]) == 1
    out = capsys.readouterr().out
    assert "bad.yaml: not valid UTF-8: byte 0xe9 at offset 37" in out
    assert "unknown_type.yaml: net.thing.oid: unknown type 'uuid'" in out


def test_main_returns_zero_on_valid():
    assert validate.main([str(FIXTURES / "valid" / "minimal.yaml")]) == 0


def test_main_returns_nonzero_on_invalid():
    assert validate.main([str(FIXTURES / "invalid" / "unknown_type.yaml")]) == 1


def test_main_returns_zero_on_real_playbooks():
    assert validate.main([str(p) for p in PLAYBOOKS]) == 0
