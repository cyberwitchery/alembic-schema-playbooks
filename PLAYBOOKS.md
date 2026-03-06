# playbook notes

this file summarizes coverage and known gaps for each schema playbook.

the playbooks are designed to be safe to provision into infrahub, among other
systems (infrahub is the most fragile at the moment). where a source system
has multiple relationships to the same peer type, only one is modeled as a
relationship and the rest are represented as plain attributes.

## servicenow-cmdb

coverage:
- configuration items (ci)
- users and locations
- services with ci membership

gaps:
- detailed class tables and class-specific attributes
- cmdb relationship tables and dependency types

## cisco-nso

coverage:
- devices, interfaces, services, ip addresses, sites

gaps:
- service-specific models and full service intent hierarchy
- detailed device module inventories

## juniper-apstra

coverage:
- blueprints, racks, devices, interfaces, links

gaps:
- full cabling model and dual-ended link references
- intent definitions and rack layout metadata

## arista-cloudvision

coverage:
- devices, interfaces, vlans, vrfs, segments

gaps:
- telemetry and event streams
- topology and l2/l3 fabrics

## infoblox

coverage:
- networks, ip addresses, dns zones, dns records, dhcp ranges, fixed addresses

gaps:
- ipv6 special objects, views/grids, and advanced policies

## solarwinds-orion

coverage:
- nodes, interfaces, volumes, alerts

gaps:
- application monitors, dependencies, and custom pollers
