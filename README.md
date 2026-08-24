# alembic schema playbooks

this directory contains alembic schema playbooks for common systems. each playbook
is a single yaml schema you can include in a brew, provision into infrahub, or use
as a starting point for adapter mapping.

## playbooks

- `servicenow-cmdb.yaml` - core cmdb configuration items and relationships.
- `cisco-nso.yaml` - device, interface, service, and ip inventory for nso/nms.
- `juniper-apstra.yaml` - blueprint, device, rack, interface, and link model.
- `arista-cloudvision.yaml` - device, interface, vlan, vrf, and segment model.
- `infoblox.yaml` - ipam/dns/dhcp core objects.
- `solarwinds-orion.yaml` - node, interface, volume, and alert inventory.
- `netbox.yaml` - netbox-lite dcim/ipam/virtualization/circuits/extras/wireless.

## usage

create a minimal brew that only includes a playbook:

```yaml
include:
  - ./alembic-schema-playbooks/servicenow-cmdb.yaml
objects: []
```

then plan and provision against infrahub:

```bash
ALEMBIC_STATE_BACKEND=local ALEMBIC_STATE_PATH=/tmp/alembic-state.json \
  cargo run -p alembic-cli -- plan \
  -f /tmp/brew.yaml \
  -o /tmp/plan.json \
  --backend-config /tmp/infrahub.yaml \
  --provision
```

## validation

every playbook is checked against the format contract documented in
[`SPEC.md`](SPEC.md) by [`validate.py`](validate.py) (standard library + pyyaml
only). run it locally:

```bash
pip install pyyaml
python3 validate.py               # validates every *.yaml in this directory
python3 validate.py netbox.yaml   # or only the files you name
```

it prints `file: type.field: message` diagnostics and exits non-zero if any
playbook is invalid. duplicate keys (a repeated type or field name, which yaml
would otherwise silently collapse to the last one) are rejected while parsing;
a key brought in by a `<<` merge is not a duplicate, and the merging mapping may
override it. ci runs the same check on every push and pull request.

## notes

- playbooks are intentionally compact and safe to provision into infrahub.
- expand fields and relationships as needed for your environment.

<hr/>

have fun!
