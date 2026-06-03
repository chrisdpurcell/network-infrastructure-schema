# NetBox mapping guide

NetBox is a **downstream projection/seed target**, not the authoring format. The
desired-state YAML is the source of truth; a generator renders NetBox REST
payloads from it. This guide gives the per-kind mapping, concrete payloads, and
the NetBox-specific quirks that bite during import.

NetBox version note: payloads below target current NetBox (4.x line). The single
biggest version-sensitive item is the **Service `parent` field** (see Services);
verify against your instance's API browser (`/api/docs/`) before bulk loads.

## Order of operations (two-pass seed)

NetBox enforces referential integrity at write time and most write payloads need
**numeric FK IDs**, not names/slugs. Follow NetBox's documented planning order
and seed in two passes:

1. **Independent objects first**, capturing the returned `id` of each:
   manufacturers → device types → device roles → sites → cluster types →
   clusters → VLAN groups → VLANs → prefix roles → prefixes.
2. **Dependent objects second**, referencing IDs from pass 1: devices →
   device interfaces → virtual machines → VM interfaces → IP addresses →
   services.

The generator keeps a name→id map in memory across the two passes. Several
inputs NetBox requires are **not present in the desired-state model** (e.g.
device `manufacturer`/`device_type`) — these are adaptation points and must be
supplied from a small seed table or sensible defaults.

## Bulk create

The REST API accepts **either a single object or a JSON array** on `POST` to a
list endpoint; an array does a bulk create in one request. Bulk update/delete
(`PATCH`/`PUT`/`DELETE` on the list endpoint) require each element to carry its
`id`. Prefer arrays to cut round-trips during seeding.

```bash
curl -sS -X POST https://netbox.example/api/ipam/vlans/ \
  -H "Authorization: Token $NETBOX_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[{"vid":10,"name":"vlan-management","status":"active"},
       {"vid":20,"name":"vlan-servers","status":"active"}]'
```

## Per-kind mapping

| Desired-state kind | NetBox endpoint | Notes |
|--------------------|-----------------|-------|
| `Site` | `dcim/sites/` | `home-fishlake` → site slug `home-fishlake`. |
| `NetworkZone` | *(no native model)* | Project to a tag and/or an IPAM Role; trustLevel becomes a tag. Adaptation point. |
| `Vlan` | `ipam/vlans/` | `vid`, `name`, `site`, optional `group`. |
| `Prefix` | `ipam/prefixes/` | `prefix`, `site`, `vlan` (id), `role`, `status`. |
| `Gateway` | IP on `ipam/ip-addresses/` | A prefix gateway is just an IP flagged via the prefix or an interface; no separate model. |
| `Device` | `dcim/devices/` | Requires `device_type`+`role`+`site` (FK ids). `device_type`/manufacturer not in model → seed table. |
| `Interface` | `dcim/interfaces/` | `device` (id), `name`, `type`. |
| `ProxmoxCluster` | `virtualization/clusters/` | Requires `type` (cluster type id). |
| `Host` | `dcim/devices/` (+ cluster) | The physical hypervisor box is a Device; its compute role is the Cluster it backs. |
| `VirtualMachine` | `virtualization/virtual-machines/` | `cluster` (id), `vcpus`, `memory` (MB), `disk` (GB). |
| `LxcContainer` | `virtualization/virtual-machines/` | NetBox has **no LXC type**; mark container vs VM with a tag or custom field. Adaptation point. |
| `Service` | `ipam/services/` | `parent` unified FK; `protocol`; `ports` (int array). See below. |
| `ServiceDependency` | *(no native model)* | Project to relationships/tags or omit; NetBox is not a dependency graph store. |
| `FirewallPolicy` / `AllowedFlow` | *(no native model)* | Not represented in NetBox; these drive firewall/Batfish generation, not the source of truth. |
| `BackupClass` / `MonitoringCheck` / `FailureScenario` | *(no native model)* | Out of NetBox scope; tags/custom fields at most. |
| `SecretRef` | *(never imported)* | Secrets must not land in NetBox. |

## Concrete payloads

### VLAN (`ipam/vlans/`)
From `Vlan/vlan-management` (vid 10):
```json
{ "vid": 10, "name": "vlan-management", "site": 1, "status": "active" }
```

### Prefix (`ipam/prefixes/`)
From `Prefix/prefix-management-v4`:
```json
{ "prefix": "10.10.10.0/24", "site": 1, "vlan": 12,
  "role": 3, "status": "active", "description": "IPv4 management subnet." }
```
NetBox auto-builds prefix/IP hierarchy: child prefixes and contained IPs nest
under this prefix automatically — you do not set parent links by hand. To query
the hierarchy, the legacy `?parent=` filter was **removed**; use
`?within=10.10.10.0/24` (strictly inside) or `?within_include=10.10.10.0/24`
(inside, including the prefix itself).

### Device (`dcim/devices/`)
From `Device/dev-k7plus`. `device_type`/`role`/`site` are FK ids resolved in
pass 1; `device_type` (and its manufacturer) is the adaptation point not carried
by the model:
```json
{ "name": "dev-k7plus", "device_type": 5, "role": 2, "site": 1,
  "status": "active", "tags": [{"name": "server"}] }
```

### Virtual machine — VM and LXC (`virtualization/virtual-machines/`)
From `VirtualMachine/vm-docker-apps`:
```json
{ "name": "vm-docker-apps", "cluster": 1, "status": "active",
  "vcpus": 4, "memory": 8192, "disk": 40,
  "tags": [{"name": "home"}, {"name": "docker"}], "custom_fields": {"guest_type": "vm"} }
```
From `LxcContainer/lxc-pihole` (same endpoint; `guest_type` distinguishes it):
```json
{ "name": "lxc-pihole", "cluster": 1, "status": "active",
  "vcpus": 2, "memory": 1024, "disk": 8,
  "tags": [{"name": "home"}, {"name": "dns"}], "custom_fields": {"guest_type": "lxc"} }
```

### VM interface + IP (`virtualization/interfaces/`, then `ipam/ip-addresses/`)
Create the interface, then bind the IP to it via `assigned_object`:
```json
{ "virtual_machine": 7, "name": "eth0", "enabled": true }
```
```json
{ "address": "10.10.10.30/24",
  "assigned_object_type": "virtualization.vminterface",
  "assigned_object_id": 41, "status": "active" }
```
The IP nests under `10.10.10.0/24` automatically.

### Service (`ipam/services/`)
From `Service/svc-pihole`. **Quirk:** current NetBox uses a single generic
`parent` reference (the UI labels it "Application Service") instead of the older
separate `device`/`virtual_machine` fields. Provide `parent_object_type` +
`parent_object_id`; `protocol` is one of `tcp|udp|sctp`; `ports` is an integer
array:
```json
{ "name": "svc-pihole",
  "parent_object_type": "virtualization.virtualmachine",
  "parent_object_id": 7,
  "protocol": "udp", "ports": [53] }
```
On older NetBox releases this is instead:
```json
{ "name": "svc-pihole", "virtual_machine": 7, "protocol": "udp", "ports": [53] }
```
The generator must branch on the target NetBox version; this is the most
common bulk-load failure for services.

## Adaptation points (summary)

- `device_type`/manufacturer for Devices are not in the model — supply a seed
  table or default.
- LXC vs VM is flattened into `virtual-machines/`; carry the distinction in a
  `guest_type` custom field or tag.
- `NetworkZone`, `ServiceDependency`, firewall, backup, monitoring, and failure
  kinds have no native NetBox models — project to tags/custom fields or treat
  NetBox as a partial projection. The desired-state repo, not NetBox, remains
  the complete record.
- Service `parent` field shape is version-sensitive; verify before bulk load.
- Never project `SecretRef` values into NetBox.
