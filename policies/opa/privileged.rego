# POLICY 3 -- No privileged LXC container unless explicitly approved.
#
# In the Proxmox/LXC model a privileged container is `spec.unprivileged: false`.
# Privileged containers share the host kernel's full capability set and are a
# real blast-radius concern, so they are denied unless the author has recorded a
# deliberate exception. The exception is carried as a well-known annotation
# rather than a first-class spec field: `metadata.annotations` is the schema's
# designated open extension point, and an approval is governance metadata, not
# desired hardware/state. The well-known key is:
#
#     infra.luminous3d.example/privileged-approved: "true"
#
# Using a string ("true") matches Kubernetes-style annotation conventions, where
# annotation values are always strings.
package main

import data.infra.lib
import rego.v1

privileged_approval_key := "infra.luminous3d.example/privileged-approved"

deny contains msg if {
	some ct in lib.by_kind("LxcContainer")
	ct.spec.unprivileged == false
	annotations := object.get(ct.metadata, "annotations", {})
	object.get(annotations, privileged_approval_key, "false") != "true"
	msg := sprintf(
		"LxcContainer/%s is privileged (unprivileged=false) without annotation %s=\"true\"",
		[ct.metadata.name, privileged_approval_key],
	)
}
