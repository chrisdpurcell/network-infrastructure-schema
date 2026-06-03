# POLICY 1 -- No public-facing service without an explicit, approved exposure
# decision.
#
# JSON Schema already forces every Service to carry an `exposure.level`. What it
# cannot express is the *governance* rule: a service reachable from the public
# internet (level=public) must be a deliberate, attributed decision. This policy
# requires approved=true plus a named approver and a written reason whenever the
# level is `public`. The Pydantic layer enforces the same invariant at author
# time (ExposureDecision validator); this Rego re-enforces it at the guardrail
# stage so it also holds for anything that reaches CI without going through the
# models.
package main

import data.infra.lib
import rego.v1

deny contains msg if {
	some svc in lib.by_kind("Service")
	svc.spec.exposure.level == "public"
	not svc.spec.exposure.approved == true
	msg := sprintf(
		"Service/%s is exposed at level=public but exposure.approved is not true",
		[svc.metadata.name],
	)
}

deny contains msg if {
	some svc in lib.by_kind("Service")
	svc.spec.exposure.level == "public"
	svc.spec.exposure.approved == true
	not lib.nonempty_string(object.get(svc.spec.exposure, "approvedBy", ""))
	msg := sprintf(
		"Service/%s is public and approved but has no exposure.approvedBy",
		[svc.metadata.name],
	)
}

deny contains msg if {
	some svc in lib.by_kind("Service")
	svc.spec.exposure.level == "public"
	svc.spec.exposure.approved == true
	not lib.nonempty_string(object.get(svc.spec.exposure, "reason", ""))
	msg := sprintf(
		"Service/%s is public and approved but has no exposure.reason",
		[svc.metadata.name],
	)
}
