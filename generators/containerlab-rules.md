# Containerlab topology generation rules

The Containerlab generator projects the **network-facing** slice of the desired
state into a [Containerlab](https://containerlab.dev/) topology so reachability
intent can be simulated and validated (typically feeding Batfish, see
`ci/pipeline.md`). Containerlab is a *test/sim* target, not a deployment target:
nothing here provisions real infrastructure.

## What maps to what

| Desired-state object | Containerlab element | Notes |
|----------------------|----------------------|-------|
| `Device` with `role` in `{firewall, router, switch}` | a `topology.nodes` entry | The routing/forwarding elements under test. Hosts that are pure compute (`role: server`) are **not** rendered as routers. |
| `NetworkZone` | a synthetic `linux` host node | One test endpoint per zone, used to assert inter-zone reachability (e.g. that `iot` cannot reach `management`). |
| Physical/logical adjacency (firewall ↔ zone) | a `topology.links` entry | Default generation is router-on-a-stick: every zone host links to the enforcing firewall. |
| Management `Prefix` | `mgmt.ipv4-subnet` | Only if you choose to align the clab mgmt net with the real management subnet; the default uses Containerlab's own mgmt range to avoid overlap (see below). |
| `FirewallPolicy` / `AllowedFlow` | rendered into each node's `startup-config` | The forwarding/filtering rules Batfish reads. Generating full vendor configs is platform-specific and flagged as an adaptation point. |

## Node kind selection

Containerlab keys behavior off `kind`. There is **no native OPNsense/pfSense
kind**, which is the main adaptation point for this environment:

- `firewall`/`router` devices default to `kind: linux` running an FRR or
  multitool image. For higher-fidelity routing/BGP tests, substitute a vendor
  kind your topology actually uses (`nokia_srlinux`, `arista_ceos`,
  `cisco_iol`) and supply the matching image.
- `switch` devices map to `kind: linux` with a bridge image, or to a real NOS
  kind if you model L2 behavior.
- Zone endpoint hosts use `kind: linux` with a small utility image
  (`ghcr.io/srl-labs/network-multitool`).

Document the chosen image per kind in `topology.kinds` so the mapping is
explicit and reproducible.

## Naming and addressing

- Node names are the `Device`/`NetworkZone` `metadata.name`, sanitized to the
  characters Containerlab allows (lowercase alphanumerics and hyphens).
- Containerlab assigns management IPs from `mgmt.ipv4-subnet`. The default
  generator uses a dedicated range (`172.20.20.0/24`) so the simulated
  management network never collides with the real management `Prefix`
  (`10.10.10.0/24`). Real data-plane addressing belongs in the rendered
  `startup-config`, not in the clab mgmt block.
- Data-plane links use the brief endpoint form
  `endpoints: ["<node>:<iface>", "<node>:<iface>"]`. Interface names are
  generated sequentially (`eth1`, `eth2`, …); `eth0`/`mgmt` is reserved for the
  management network.

## Provenance of the example

`examples/containerlab/generated-topology.clab.yaml` is generated assuming a
home site that declares the firewall `dev-opnsense` plus four zones
(`zone-management`, `zone-servers`, `zone-iot`, `zone-guest`). The home manifest
in `examples/manifests/site-home.yaml` declares the first two; `zone-iot` and
`zone-guest` are present as per-kind examples. The four-zone projection is used
because it exercises the management-isolation policy (Batfish then proves that
`iot`/`guest` endpoints cannot reach the `management` endpoint). Regenerating
from a manifest that declares fewer zones simply yields fewer host nodes.

## Validation status

The example topology is validated for YAML syntax and for conformance to the
Containerlab topology schema fields documented at
<https://containerlab.dev/manual/topo-def-file/> (top-level `name`, `mgmt`,
`topology.{defaults,kinds,nodes,links}`). It is **not** deployed in CI here,
because `containerlab deploy` requires Docker and root. In CI,
`containerlab inspect --topo <file>` / a schema lint validates structure
without standing up containers; full deploy runs on a runner that has Docker.
