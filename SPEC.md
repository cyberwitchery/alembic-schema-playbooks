# playbook format specification

this document defines the contract that every `*.yaml` playbook in this repo
must satisfy. it is enforced by [`validate.py`](validate.py); see
[README](README.md#validation) for how to run it.

the format is intentionally small: a playbook declares a set of typed objects
and the fields (including relationships) each object carries.

## document shape

each playbook is a standalone YAML document shaped as:

```yaml
schema:
  types:
    <namespace>.<type>:
      key:
        <field>: { type: <T> }
      fields:
        <field>: { type: <T> }
        <other>: { type: <T>, required: true }
        # ...
```

- the file is encoded as UTF-8. YAML also allows UTF-16, but a playbook must
  not use it.
- the top-level document is a mapping with a `schema` mapping containing a
  `types` mapping.
- each entry under `types` is keyed by a `<namespace>.<type>` name (for example
  `dcim.device`) — exactly two non-empty `.`-separated segments. namespaces are
  **file-scoped**: two playbooks may reuse the same namespace without conflict,
  and references never cross files.
- each type definition has a `key` mapping and a `fields` mapping.
  - `fields` declares every field of the type.
  - `key` declares the subset of fields that identify an instance. a key may
    name several fields, but must name at least one, and none of them may be a
    `list`, a `list_ref` or `nullable`. every field named in `key` must also be
    declared in `fields`, and the two specs must be **identical**: the same
    `type`, the same extra key that type requires (`target` for
    `ref`/`list_ref`, `values` for `enum`, `item` for `list`) and the same
    metadata. a key field is always required, so neither copy needs to say so.
- a **field spec** is a mapping with a `type` and optional extra keys
  (`required`, `values`, `target`, `item`, ...). field specs appear under both
  `key` and `fields`, and inside a `list` item; they are validated the same way
  wherever they appear.
- YAML anchors and the `<<` merge key may be used freely. an anchored mapping
  may be aliased (`*name`) or merged into another mapping (`<<: *name`, or
  `<<: [*a, *b]` to merge several — earlier aliases win), and the merging
  mapping's own keys override the merged ones. merges are resolved before the
  rules below are checked, so a merged field spec is validated exactly as if it
  had been written out in place; the one rule that looks at the unmerged text is
  rule 9, which counts only the keys a mapping writes itself. a `<<` whose value
  is neither a mapping nor a list of mappings is a YAML parse error.

## field types

`type` must be one of:

| type         | extra keys required          | notes                                   |
| ------------ | ---------------------------- | --------------------------------------- |
| `string`     | —                            | short text                              |
| `text`       | —                            | long / multi-line text                  |
| `bool`       | —                            | boolean                                 |
| `int`        | —                            | integer                                 |
| `float`      | —                            | floating point                          |
| `enum`       | `values: [...]` (non-empty)  | one of a fixed set of values            |
| `ip_address` | —                            | an IPv4/IPv6 host address               |
| `mac`        | —                            | a MAC address                           |
| `prefix`     | —                            | an IP network prefix (CIDR)             |
| `slug`       | —                            | a url-safe identifier                   |
| `ref`        | `target: <ns>.<type>`        | a single relationship to another type   |
| `list_ref`   | `target: <ns>.<type>`        | a multi relationship to another type    |
| `list`       | `item: { type: <T> }`        | a list of scalar/typed items            |

`required`, `nullable`, `format`, `pattern` and `description` are metadata and
may appear on any field spec; only rules 10 and 14 constrain them. any other
extra keys are ignored.

## validation rules

`validate.py` reports one `file: type.field: message` diagnostic per problem and
exits non-zero if any playbook is invalid. the rules are:

1. **schema.types present** — the top-level document is a mapping and
   `schema.types` is a mapping. otherwise: `missing 'schema.types' mapping`.
2. **key and fields present** — every type definition is a mapping with both a
   `key` mapping and a `fields` mapping. otherwise: `missing 'key' mapping` /
   `missing 'fields' mapping`.
3. **known type** — every field spec has a `type`, and that `type` is one of the
   vocabulary above. otherwise: `missing 'type'` / `'type' must be a string` /
   `unknown type '<T>'`.
4. **enum values** — an `enum` field has a non-empty `values` list. otherwise:
   `enum requires a non-empty 'values' list`.
5. **ref target present** — a `ref` / `list_ref` field has a non-empty `target`
   string. otherwise: `<type> requires a 'target'`.
6. **list item present** — a `list` field has an `item` mapping with a `type`
   (validated recursively). otherwise: `list requires 'item.type'`.
7. **ref target resolves** — every `ref` / `list_ref` `target` names a type
   defined **within the same file**. otherwise:
   `<type> target '<name>' is not defined in this file`.
8. **key field declared** — every field named under `key` also appears under
   `fields`. otherwise: `key field not present in 'fields'`.
9. **unique keys** — no mapping repeats a key it writes out itself. a duplicate
   type name under `schema.types`, a duplicate field name under `key`/`fields`,
   or a repeated key inside a field spec is rejected while parsing — YAML would
   otherwise silently keep only the last, dropping the earlier definition. a key
   a `<<` brings in is not a repeat: YAML defines the explicit key as winning,
   so nothing is dropped silently, and overriding one merged entry is the point
   of the idiom. each merged mapping is checked for repeats where it is written.
   the first duplicate is reported and parsing of that file stops. otherwise:
   `duplicate key '<key>'`.
10. **key and fields agree** — where a field is declared under both `key` and
    `fields`, the two specs are identical as alembic reads them: the same
    `type`, the same extra key that type requires (`target` for
    `ref`/`list_ref`, `values` for `enum`, `item` for `list`), and the same
    `required`, `nullable`, `format`, `pattern` and `description`, an absent
    `required` or `nullable` reading as `false`. these are compared by type as
    well as by value, item by item: `1`, `1.0` and `true` are three different
    values, so `values: [1, 0]` does not agree with `values: [true, false]`.
    a `list`'s `item` is a bare type to alembic, so two `item` specs are
    compared on `type` and its extra key alone, at every depth; a nested
    disagreement is reported against the item, as `<type>.<field>.item`. only
    the first disagreement is reported. otherwise:
    `'key' and 'fields' disagree on '<attr>': <key value> vs <fields value>`.
11. **key is non-empty** — a `key` mapping names at least one field; a type
    whose instances nothing identifies is meaningless. otherwise:
    `'key' must declare at least one field`.
12. **dotted type name** — every entry under `schema.types` is named
    `<namespace>.<type>`: exactly two non-empty `.`-separated segments. only
    that shape is checked; which characters a segment uses is unconstrained.
    otherwise: `type name must be '<namespace>.<type>'`.
13. **no self-nesting field spec** — no field spec contains itself. a YAML
    anchor aliased inside the node it names makes a spec its own `item`, which
    describes a list of unbounded depth that no document can satisfy. it is the
    nesting that is rejected, not the sharing: one anchored spec reused by two
    sibling fields is fine. otherwise: `field spec nests itself`.
14. **key field not nullable** — a field under `key` is not `nullable: true`;
    a null has no identity. otherwise: `key field may not be nullable`.
15. **key field not composite** — a field under `key` is not a `list` or a
    `list_ref`; neither has a scalar identity. otherwise:
    `key field may not be a <type>`.

rules 3–7 and 13 apply to every field spec, including those under `key` and
those nested in a `list` item; rule 10 likewise compares a key field's two
declarations at every depth. rules 14 and 15 look only at the spec under `key`,
and rule 10 holds the `fields` copy to it. rule 10 completes rule 8: rule 8
requires a key field to be declared under `fields` at all, rule 10 requires the
two declarations to say the same thing.

no single playbook can stop the others from being checked. a file the validator
cannot walk to the end — nested deeper than it can descend, or self-referential
through YAML anchors — is reported as
`too deeply nested or self-referential to validate` and the run carries on with
the rest. the same goes for a file it cannot load: one it cannot read is
reported as `cannot read file: <reason>`, one that is not UTF-8 as
`not valid UTF-8: byte 0x<hh> at offset <n>`, where `<n>` is the number of
bytes before the offending one, and one that is not well-formed YAML as
`YAML parse error: <details>`.

a playbook that violates none of these rules is valid. the validator does not
check field *values* (there are none in a playbook) — only the schema shape.
