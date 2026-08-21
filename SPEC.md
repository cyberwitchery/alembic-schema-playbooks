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
        <field>: { type: <T>, required: true }
        # ...
```

- the top-level document is a mapping with a `schema` mapping containing a
  `types` mapping.
- each entry under `types` is keyed by a `<namespace>.<type>` name (for example
  `dcim.device`) — exactly two non-empty `.`-separated segments. namespaces are
  **file-scoped**: two playbooks may reuse the same namespace without conflict,
  and references never cross files.
- each type definition has a `key` mapping and a `fields` mapping.
  - `fields` declares every field of the type.
  - `key` declares the subset of fields that identify an instance. a key may be
    composite (several fields), but must name at least one. every field named
    in `key` must also be declared in `fields`, and the two specs must **agree**
    on what the field is: the same `type`, and the same extra key that type
    requires (`target` for `ref`/`list_ref`, `values` for `enum`, `item` for
    `list`). for a `list`, the two `item` specs must agree by this same rule,
    recursively. metadata may differ — playbooks conventionally mark `required`
    only under `fields`.
- a **field spec** is a mapping with a `type` and optional extra keys
  (`required`, `values`, `target`, `item`, ...). field specs appear under both
  `key` and `fields`, and inside a `list` item; they are validated the same way
  wherever they appear.

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

`required: true` may appear on any field spec; it is metadata and is not
otherwise constrained. any other extra keys are ignored.

## validation rules

`validate.py` reports one `file: type.field: message` diagnostic per problem and
exits non-zero if any playbook is invalid. the rules are:

1. **schema.types present** — the top-level document is a mapping and
   `schema.types` is a mapping. otherwise: `missing 'schema.types' mapping`.
2. **key and fields present** — every type definition is a mapping with both a
   `key` mapping and a `fields` mapping. otherwise: `missing 'key' mapping` /
   `missing 'fields' mapping`.
3. **known type** — every field spec has a `type`, and that `type` is one of the
   vocabulary above. otherwise: `missing 'type'` / `unknown type '<T>'`.
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
9. **unique keys** — no mapping repeats a key. a duplicate type name under
   `schema.types`, a duplicate field name under `key`/`fields`, or a repeated
   key inside a field spec is rejected while parsing — YAML would otherwise
   silently keep only the last, dropping the earlier definition. the first
   duplicate is reported and parsing of that file stops. otherwise:
   `duplicate key '<key>'`.
10. **key and fields agree** — where a field is declared under both `key` and
    `fields`, the two specs name the same `type` and the same extra key that
    type requires (`target` for `ref`/`list_ref`, `values` for `enum`, `item`
    for `list`). anything else, `required` included, may differ. a `list`'s two
    `item` specs are compared by this same rule rather than for equality, so it
    holds at every depth — metadata nested inside an item may differ too, and a
    nested disagreement is reported against the item, as
    `<type>.<field>.item`. otherwise:
    `'key' and 'fields' disagree on '<attr>': <key value> vs <fields value>`.
11. **key is non-empty** — a `key` mapping names at least one field; a type
    whose instances nothing identifies is meaningless. otherwise:
    `'key' must declare at least one field`.
12. **dotted type name** — every entry under `schema.types` is named
    `<namespace>.<type>`: exactly two non-empty `.`-separated segments. only
    that shape is checked; which characters a segment uses is unconstrained.
    otherwise: `type name must be '<namespace>.<type>'`.

rules 3–7 apply to every field spec, including those under `key` and those
nested in a `list` item; rule 10 likewise compares a key field's two
declarations at every depth. rule 10 completes rule 8: rule 8 requires a key
field to be declared under `fields` at all, rule 10 requires the two
declarations to say the same thing.

a playbook that violates none of these rules is valid. the validator does not
check field *values* (there are none in a playbook) — only the schema shape.
