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

## notes

- playbooks are intentionally compact and safe to provision into infrahub.
- expand fields and relationships as needed for your environment.

<hr/>

have fun!
