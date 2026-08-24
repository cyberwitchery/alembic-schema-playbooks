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
    "list_item_metadata.yaml",
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
    ("list_item_disagree.yaml", "'key' and 'fields' disagree on 'target'"),
    ("empty_key.yaml", "'key' must declare at least one field"),
    ("undotted_type_name.yaml", "type name must be '<namespace>.<type>'"),
    ("bad_yaml.yaml", "YAML parse error"),
    ("self_nesting_item.yaml", "field spec nests itself"),
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


def test_key_and_fields_may_differ_on_metadata(tmp_path):
    # every shipped playbook marks 'required' only under 'fields'
    playbook = tmp_path / "m.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {x: {type: enum, values: [one, two]}}\n"
        "      fields: {x: {type: enum, values: [one, two], required: true}}\n"
    )
    assert validate.validate_file(playbook) == []


def test_key_and_fields_may_differ_on_metadata_inside_a_list_item(tmp_path):
    playbook = tmp_path / "i.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {t: {type: list, item: {type: string}}}\n"
        "      fields: {t: {type: list, item: {type: string, required: true}}}\n"
    )
    assert validate.validate_file(playbook) == []


def test_key_and_fields_list_item_type_disagreement_is_rejected(tmp_path):
    playbook = tmp_path / "n.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {t: {type: list, item: {type: string}}}\n"
        "      fields: {t: {type: list, item: {type: int}}}\n"
    )
    assert validate.validate_file(playbook) == [
        "n.yaml: a.b.t.item: 'key' and 'fields' disagree on 'type': 'string' vs 'int'"
    ]


def test_key_and_fields_nested_list_item_is_compared_at_depth(tmp_path):
    playbook = tmp_path / "z.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {t: {type: list, item: {type: list, item: "
        "{type: enum, values: [one]}}}}\n"
        "      fields: {t: {type: list, item: {type: list, item: "
        "{type: enum, values: [two], required: true}}}}\n"
    )
    expected = (
        "z.yaml: a.b.t.item.item: 'key' and 'fields' disagree on 'values': "
        "['one'] vs ['two']"
    )
    assert validate.validate_file(playbook) == [expected]


def test_malformed_list_item_is_reported_once(tmp_path):
    playbook = tmp_path / "o.yaml"
    playbook.write_text(
        "schema:\n  types:\n    a.b:\n"
        "      key: {t: {type: list, item: {type: string}}}\n"
        "      fields: {t: {type: list}}\n"
    )
    assert validate.validate_file(playbook) == [
        "o.yaml: a.b.t: list requires 'item.type'"
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


def test_main_returns_zero_on_valid():
    assert validate.main([str(FIXTURES / "valid" / "minimal.yaml")]) == 0


def test_main_returns_nonzero_on_invalid():
    assert validate.main([str(FIXTURES / "invalid" / "unknown_type.yaml")]) == 1


def test_main_returns_zero_on_real_playbooks():
    assert validate.main([str(p) for p in PLAYBOOKS]) == 0
