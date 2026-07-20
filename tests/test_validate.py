from pathlib import Path

import pytest

import validate

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PLAYBOOKS = sorted(REPO_ROOT.glob("*.yaml"))


def test_valid_fixture_passes():
    assert validate.validate_file(FIXTURES / "valid" / "minimal.yaml") == []


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
    ("key_fields_disagree.yaml", "'key' and 'fields' disagree on 'type'"),
    ("empty_key.yaml", "'key' must declare at least one field"),
    ("undotted_type_name.yaml", "type name must be '<namespace>.<type>'"),
    ("bad_yaml.yaml", "YAML parse error"),
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


def test_main_returns_zero_on_valid():
    assert validate.main([str(FIXTURES / "valid" / "minimal.yaml")]) == 0


def test_main_returns_nonzero_on_invalid():
    assert validate.main([str(FIXTURES / "invalid" / "unknown_type.yaml")]) == 1


def test_main_returns_zero_on_real_playbooks():
    assert validate.main([str(p) for p in PLAYBOOKS]) == 0
