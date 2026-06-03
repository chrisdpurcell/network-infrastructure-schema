# Unit tests for the guardrail policies, runnable with `conftest verify -p
# policies/opa`. Each policy has at least one passing case (no deny) and one
# failing case (deny fires). Inputs mimic the `conftest test --combine` shape:
# an array of {path, contents} entries, which the shared lib flattens.
package main

import rego.v1

# Helper: wrap a list of objects as a combined-input array.
combined(objs) := [entry |
	some o in objs
	entry := {"path": "test", "contents": o}
]

# ---- Policy 1: public exposure ----------------------------------------------

svc_public_ok := {
	"apiVersion": "infra.luminous3d.example/v1alpha1",
	"kind": "Service",
	"metadata": {"name": "svc-public"},
	"spec": {
		"runsOn": {"kind": "VirtualMachine", "name": "vm-edge"},
		"serviceType": "web",
		"criticality": "high",
		"exposure": {
			"level": "public",
			"approved": true,
			"approvedBy": "chris",
			"reason": "Public marketing site, WAF in front.",
		},
	},
}

test_public_service_approved_passes if {
	count(deny) == 0 with input as combined([svc_public_ok])
}

test_public_service_unapproved_denies if {
	bad := json.patch(svc_public_ok, [{"op": "replace", "path": "/spec/exposure/approved", "value": false}])
	count(deny) == 1 with input as combined([bad])
}

test_public_service_missing_reason_denies if {
	bad := json.remove(svc_public_ok, ["/spec/exposure/reason"])
	count(deny) == 1 with input as combined([bad])
}

# ---- Policy 2: critical service backup --------------------------------------

bc_ok := {
	"apiVersion": "infra.luminous3d.example/v1alpha1",
	"kind": "BackupClass",
	"metadata": {"name": "backup-critical"},
	"spec": {"schedule": "0 2 * * *", "target": "pbs:home", "restoreTarget": "pbs:home -> host-k7plus"},
}

svc_critical_ok := {
	"apiVersion": "infra.luminous3d.example/v1alpha1",
	"kind": "Service",
	"metadata": {"name": "svc-dns"},
	"spec": {
		"runsOn": {"kind": "LxcContainer", "name": "lxc-pihole"},
		"serviceType": "dns",
		"criticality": "critical",
		"exposure": {"level": "lan"},
		"backupClass": {"kind": "BackupClass", "name": "backup-critical"},
	},
}

test_critical_with_backup_and_restore_passes if {
	count(deny) == 0 with input as combined([svc_critical_ok, bc_ok])
}

test_critical_without_backupclass_denies if {
	bad := json.remove(svc_critical_ok, ["/spec/backupClass"])
	count(deny) == 1 with input as combined([bad])
}

test_critical_backupclass_missing_restoretarget_denies if {
	bc_bad := json.remove(bc_ok, ["/spec/restoreTarget"])
	count(deny) == 1 with input as combined([svc_critical_ok, bc_bad])
}

test_critical_unresolvable_backupclass_denies if {
	count(deny) == 1 with input as combined([svc_critical_ok])
}

# ---- Policy 3: privileged container -----------------------------------------

lxc_unpriv := {
	"apiVersion": "infra.luminous3d.example/v1alpha1",
	"kind": "LxcContainer",
	"metadata": {"name": "lxc-safe"},
	"spec": {"unprivileged": true},
}

lxc_priv_approved := {
	"apiVersion": "infra.luminous3d.example/v1alpha1",
	"kind": "LxcContainer",
	"metadata": {
		"name": "lxc-gpu",
		"annotations": {"infra.luminous3d.example/privileged-approved": "true"},
	},
	"spec": {"unprivileged": false},
}

test_unprivileged_container_passes if {
	count(deny) == 0 with input as combined([lxc_unpriv])
}

test_privileged_approved_passes if {
	count(deny) == 0 with input as combined([lxc_priv_approved])
}

test_privileged_unapproved_denies if {
	bad := json.remove(lxc_priv_approved, ["/metadata/annotations"])
	count(deny) == 1 with input as combined([bad])
}

# ---- Policy 4: management isolation -----------------------------------------

zone_mgmt := {"apiVersion": "infra.luminous3d.example/v1alpha1", "kind": "NetworkZone", "metadata": {"name": "zone-management"}, "spec": {"site": {"kind": "Site", "name": "s"}, "trustLevel": "management"}}

zone_iot := {"apiVersion": "infra.luminous3d.example/v1alpha1", "kind": "NetworkZone", "metadata": {"name": "zone-iot"}, "spec": {"site": {"kind": "Site", "name": "s"}, "trustLevel": "iot"}}

zone_trusted := {"apiVersion": "infra.luminous3d.example/v1alpha1", "kind": "NetworkZone", "metadata": {"name": "zone-trusted"}, "spec": {"site": {"kind": "Site", "name": "s"}, "trustLevel": "trusted"}}

fw_iot_trusted := {"apiVersion": "infra.luminous3d.example/v1alpha1", "kind": "FirewallPolicy", "metadata": {"name": "fw-ok"}, "spec": {"defaultAction": "drop", "appliesTo": "zone-pair", "device": {"kind": "Device", "name": "d"}, "fromZone": {"kind": "NetworkZone", "name": "zone-iot"}, "toZone": {"kind": "NetworkZone", "name": "zone-trusted"}}}

fw_iot_mgmt := json.patch(fw_iot_trusted, [{"op": "replace", "path": "/spec/toZone/name", "value": "zone-management"}])

test_iot_to_trusted_passes if {
	count(deny) == 0 with input as combined([zone_iot, zone_trusted, fw_iot_trusted])
}

test_iot_to_management_denies if {
	count(deny) == 1 with input as combined([zone_iot, zone_mgmt, fw_iot_mgmt])
}

# ---- Policy 5: IP within prefix ---------------------------------------------

prefix_mgmt := {"apiVersion": "infra.luminous3d.example/v1alpha1", "kind": "Prefix", "metadata": {"name": "p-mgmt"}, "spec": {"cidr": "10.10.10.0/24", "site": {"kind": "Site", "name": "s"}, "role": "management"}}

lxc_in_prefix := {"apiVersion": "infra.luminous3d.example/v1alpha1", "kind": "LxcContainer", "metadata": {"name": "lxc-net"}, "spec": {"unprivileged": true, "networkInterfaces": [{"name": "eth0", "bridge": "vmbr0", "ipv4": {"address": "10.10.10.30/24"}}]}}

lxc_out_of_prefix := json.patch(lxc_in_prefix, [{"op": "replace", "path": "/spec/networkInterfaces/0/ipv4/address", "value": "192.168.50.5/24"}])

test_ip_in_prefix_passes if {
	count(deny) == 0 with input as combined([prefix_mgmt, lxc_in_prefix])
}

test_ip_out_of_prefix_denies if {
	count(deny) == 1 with input as combined([prefix_mgmt, lxc_out_of_prefix])
}

test_dhcp_interface_is_ignored if {
	dhcp := json.patch(lxc_in_prefix, [{"op": "replace", "path": "/spec/networkInterfaces/0/ipv4/address", "value": "dhcp"}])
	count(deny) == 0 with input as combined([prefix_mgmt, dhcp])
}
