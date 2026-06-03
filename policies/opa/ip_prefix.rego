# POLICY 5 -- Every statically-assigned guest IP must fall within a declared
# Prefix.
#
# This walks every VirtualMachine and LxcContainer network interface, takes the
# IPv4 host address (ignoring DHCP), strips the mask, and requires that it be
# contained by at least one Prefix.spec.cidr in the desired state. OPA's
# built-in `net.cidr_contains` does the containment test natively. The Pydantic
# graph layer performs the identical check at author time; this policy is the
# guardrail-stage backstop and also documents the invariant for reviewers.
package main

import data.infra.lib
import rego.v1

guest_kinds := {"VirtualMachine", "LxcContainer"}

# All declared IPv4 prefixes (CIDR strings).
prefixes contains cidr if {
	some p in lib.by_kind("Prefix")
	cidr := p.spec.cidr
}

# (object, nicName, hostIP) triples for every static IPv4 assignment.
assignments contains [obj, nic.name, host_ip] if {
	some obj in lib.objects
	obj.kind in guest_kinds
	some nic in obj.spec.networkInterfaces
	addr := nic.ipv4.address
	addr != "dhcp"
	host_ip := split(addr, "/")[0]
}

deny contains msg if {
	some a in assignments
	obj := a[0]
	nic_name := a[1]
	host_ip := a[2]
	not within_any_prefix(host_ip)
	msg := sprintf(
		"%s/%s interface %s address %s is not within any declared Prefix",
		[obj.kind, obj.metadata.name, nic_name, host_ip],
	)
}

within_any_prefix(host_ip) if {
	some cidr in prefixes
	net.cidr_contains(cidr, host_ip)
}
