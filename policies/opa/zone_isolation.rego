# POLICY 4 -- The management zone must be isolated from guest and IoT zones.
#
# "Isolation" is enforced over declared zone pairs in the desired state. Two
# kinds carry an explicit zone-to-zone relationship:
#   * FirewallPolicy -> spec.fromZone / spec.toZone
#   * AllowedFlow    -> spec.source.zone / spec.destination.zone
# For each such pair this policy resolves both NetworkZone objects and reads
# their trustLevel. If one side is `management` and the other is `guest` or
# `iot`, the pair is a violation regardless of direction -- the management plane
# must never share a reachability edge with low-trust device networks.
#
# LIMITATION (documented, by design): when an AllowedFlow names a Service as its
# endpoint rather than a zone, this policy does not infer that service's zone
# (that requires guest -> NIC VLAN -> Vlan -> zone resolution, which belongs in
# the Batfish/Containerlab reachability layer, not a static policy). Such flows
# are still governed by their owning FirewallPolicy's declared zone pair, which
# this policy does evaluate. Batfish is the backstop for emergent reachability.
package main

import data.infra.lib
import rego.v1

low_trust := {"guest", "iot"}

# trustLevel of the NetworkZone named by a zone ref, if resolvable.
zone_trust(ref) := tl if {
	z := lib.resolve(ref)
	z.kind == "NetworkZone"
	tl := z.spec.trustLevel
}

# Ordered pairs of (zoneRefA, zoneRefB) declared by FirewallPolicy objects.
zone_pairs contains [a, b] if {
	some fw in lib.by_kind("FirewallPolicy")
	a := fw.spec.fromZone
	b := fw.spec.toZone
}

# ...and by AllowedFlow objects that use zone endpoints on both sides.
zone_pairs contains [a, b] if {
	some fl in lib.by_kind("AllowedFlow")
	a := fl.spec.source.zone
	b := fl.spec.destination.zone
}

deny contains msg if {
	some pair in zone_pairs
	ta := zone_trust(pair[0])
	tb := zone_trust(pair[1])
	management_low_trust_pair(ta, tb)
	msg := sprintf(
		"zone pair %s(%s) <-> %s(%s) violates management isolation; management must not share a reachability edge with guest or IoT",
		[pair[0].name, ta, pair[1].name, tb],
	)
}

# True when one side is management and the other is guest/iot (either order).
management_low_trust_pair(ta, tb) if {
	ta == "management"
	tb in low_trust
}

management_low_trust_pair(ta, tb) if {
	tb == "management"
	ta in low_trust
}
