# POLICY 2 -- A critical service must declare a backup class, and that backup
# class must define a restore target.
#
# This is a two-hop, cross-object rule that JSON Schema cannot express: it
# starts at a Service, requires `spec.backupClass`, then follows that reference
# to the BackupClass object and checks that it carries a non-empty
# `restoreTarget`. A backup with no defined restore path is a false sense of
# safety, so "critical" is gated on both halves being present.
package main

import data.infra.lib
import rego.v1

# Critical service with no backupClass reference at all.
deny contains msg if {
	some svc in lib.by_kind("Service")
	svc.spec.criticality == "critical"
	not svc.spec.backupClass
	msg := sprintf(
		"Service/%s is criticality=critical but declares no backupClass",
		[svc.metadata.name],
	)
}

# backupClass reference present but unresolvable in the evaluated set.
deny contains msg if {
	some svc in lib.by_kind("Service")
	svc.spec.criticality == "critical"
	ref := svc.spec.backupClass
	not lib.resolve(ref)
	msg := sprintf(
		"Service/%s references BackupClass/%s which is not defined",
		[svc.metadata.name, ref.name],
	)
}

# Resolved BackupClass is missing a restore target.
deny contains msg if {
	some svc in lib.by_kind("Service")
	svc.spec.criticality == "critical"
	bc := lib.resolve(svc.spec.backupClass)
	bc.kind == "BackupClass"
	not lib.nonempty_string(object.get(bc.spec, "restoreTarget", ""))
	msg := sprintf(
		"Service/%s uses BackupClass/%s which has no restoreTarget",
		[svc.metadata.name, bc.metadata.name],
	)
}
