# Original prompt (reconstructed)

Verbatim-reconstructed prompt that produced the infra-schema pack. The original attachment text was not retained in working context, so this is a reconstruction. Linked from `PROJECT-STATUS-AND-ROADMAP.md` §1 (and noted in its §4).

```markdown
You are a senior infrastructure schema architect with web-browsing capability. Research and author a complete schema pack for a homegrown desired-state infrastructure model for a greenfield infrastructure repo.

Minimal context:

- The repo is the canonical intent layer for a greenfield rebuild of a small/home infrastructure environment.
- Hand-authored YAML files define intended network, hosts, Proxmox clusters, VMs/LXC containers, services, dependencies, firewall intent, backups, monitoring, and failure scenarios.
- Downstream generators will produce: NetBox seed/import payloads, OpenTofu/Terraform HCL for Proxmox, Ansible inventories/vars, Containerlab topologies, and Batfish inputs/tests.
- The hand-authored desired-state files should use an envelope inspired by Kubernetes/Backstage: apiVersion, kind, metadata, spec.
- Treat the YAML as desired state only; do not model live/observed status in hand-authored files unless you explicitly justify a narrow exception.
- Never put plaintext secrets in the desired-state model; use SecretRef objects only.
- NetBox is a downstream projection/seed target, not the primary authoring format.
- Docker Compose may be referenced only as an implementation example for generated service configs; it should not shape the core desired-state schema.

Your task: Research the relevant authoritative standards/docs, then design and author the schema, examples, mappings, policies, and implementation guidance.

Required research areas:

1. NetBox data model and REST/API/import implications.
2. Kubernetes + Backstage apiVersion-kind-metadata-spec envelope patterns.
3. JSON Schema 2020-12 validation patterns and best practices.
4. YANG/OpenConfig concepts for network/interface/VLAN/prefix modeling.
5. Containerlab topology schema and topology-as-code conventions.
6. OpenTofu/Terraform Proxmox provider resources for VM/LXC creation (prefer current bpg/proxmox docs).
7. Docker Compose service fields only as implementation examples.
8. IaC policy/guardrail tools: OPA/Rego, Conftest, Checkov, Trivy.
9. CI validation flow including OpenTofu, ansible-lint, Containerlab, and Batfish.

Object kinds that MUST be covered:

- Site
- NetworkZone
- Vlan
- Prefix
- Gateway
- Device
- Interface
- ProxmoxCluster
- Host
- VirtualMachine
- LxcContainer
- Service
- ServiceDependency
- FirewallPolicy
- AllowedFlow
- BackupClass
- SecretRef
- MonitoringCheck
- FailureScenario

Hard requirements:

1. Produce a comprehensive JSON Schema using JSON Schema Draft 2020-12 that validates the YAML desired-state files.
2. Use a shared envelope (apiVersion, kind, metadata, spec) and design reusable $defs/shared definitions where appropriate.
3. Be explicit about how validation works for:
   - single-object files
   - multi-object bundles/manifests
   - multi-document YAML streams if you choose to support them
4. Where JSON Schema cannot practically enforce cross-object or graph constraints, explicitly document what is instead enforced by:
   - Pydantic validators
   - OPA/Conftest policies
   - generated-environment tests (Containerlab/Batfish/OpenTofu/etc.)
5. Produce valid YAML examples for every kind listed above.
6. Produce at least two multi-object example manifests:
   - one single-site manifest with hosts + vlans + prefixes + services
   - one multi-site manifest with failover + failure-scenario modeling
7. Produce Pydantic v2 Python models that map cleanly to the schema and include JSON Schema export.
8. Produce a mapping guide showing how YAML objects map to NetBox seed/import payloads, with concrete examples for:
   - devices
   - VMs/LXCs
   - prefixes
   - IPs
   - VLANs
   - services
9. Produce Containerlab topology generation rules and one generated example topology YAML from the model.
10. Produce OpenTofu/Terraform mapping guidance for the current Proxmox provider and include example HCL snippets generated from the model for:

- at least one VM
- at least one LXC container

11. Produce validation/policy rules in OPA/Rego and Conftest tests for at least these five policies:

- no public-facing service without an explicit exposure decision
- critical service must have backup class and restore target
- no privileged container unless explicitly approved
- management VLAN must be isolated from guest and IoT
- IPs must be within defined prefixes

12. Explain where Checkov and Trivy fit:

- abstract model vs generated artifacts
- what they can realistically scan
- how to wire them into CI

13. Include CI pipeline steps with commands and order to:

- validate YAML syntax
- run JSON Schema validation
- run Pydantic validation checks
- run OPA/Conftest
- run Checkov/Trivy where applicable
- run OpenTofu validate/plan
- run ansible-lint
- run Batfish/Containerlab tests (describe expected inputs/outputs)
- produce artifacts (NetBox seed payloads, OpenTofu plan artifacts, Ansible inventories)

14. Produce a short README template describing:

- how to author the YAML
- how to validate it
- how to generate artifacts
- how to integrate with NetBox / OpenTofu / Ansible / Containerlab / Batfish

15. Produce a changelog template and versioning guidance for the schema.
16. Produce both:

- machine-readable outputs
- a human-readable report summarizing design decisions, assumptions, tradeoffs, and limitations

17. Be explicit about assumptions and flag any area where vendor-specific details may require adaptation.

Design expectations:

- Prefer JSON Schema 2020-12.
- Prefer Pydantic v2.
- Prefer the current Containerlab schema/docs.
- Prefer current OpenTofu/Terraform bpg/proxmox provider docs, not legacy Telmate material unless you mention it only as historical context.
- Prefer official docs and standards first. Only use source code/repos when official docs are missing detail.
- Keep the schema opinionated enough to be useful:
  - use closed schemas (`additionalProperties: false`) where practical
  - reserve explicit extension points where needed (for example labels/annotations)
- Use clear object references and naming conventions; explain whether references are by name, UID, path, or composite key.
- Clearly define the semantic boundaries between overlapping kinds such as Device vs Host, Host vs VirtualMachine, Gateway vs Interface, FirewallPolicy vs AllowedFlow, Service vs ServiceDependency.
- Use SecretRef for secret references only; never embed the secret values.
- Use Docker Compose only as a generated implementation example for relevant containerized services; do not make Compose the root model.
- Distinguish “what the desired state is” from “how a tool implements it.”

Output format: Return everything in one response. Use this exact structure:

1. Research summary and design decisions
2. Assumptions, limitations, and enforcement-boundary matrix
3. Prioritized source list with links and citations
4. Proposed repo layout
5. FILE: schemas/infra.schema.json
6. FILE: python/infra_models.py
7. FILE: examples/kinds/<one yaml example per kind>...
8. FILE: examples/manifests/site-home.yaml
9. FILE: examples/manifests/multi-site-failover.yaml
10. FILE: mappings/netbox-mapping-guide.md
11. FILE: generators/containerlab-rules.md
12. FILE: examples/containerlab/generated-topology.clab.yaml
13. FILE: generators/proxmox-opentofu-mapping-guide.md
14. FILE: examples/opentofu/proxmox-example.tf
15. FILE: policies/opa/<rego files>
16. FILE: policies/conftest/<tests or notes on invocation>
17. FILE: ci/pipeline.md
18. FILE: README.md
19. FILE: CHANGELOG.md
20. Final human-readable report

For every FILE section:

- Put the file path on the heading line exactly as `FILE: path/to/file`
- Then provide the full file contents in a fenced code block
- Do not use placeholders like “...” or “omitted for brevity”
- The JSON Schema must be complete and runnable
- The Python module must be complete and syntactically valid
- YAML examples must be internally consistent with the schema
- Policies must be concrete and runnable or clearly marked if pseudocode is unavoidable for a specific tool limitation

Additional requirements:

- Cite authoritative sources throughout the report, not just at the end.
- If sources disagree, say so and explain which choice you made and why.
- If a requirement is better enforced outside JSON Schema, say that explicitly and implement it in the correct layer.
- Flag any vendor-specific adaptation points, especially for:
  - NetBox import/REST payload quirks
  - Proxmox provider fields and cloud-init specifics
  - Containerlab node kinds/images
  - Batfish input expectations and supported configs
  - firewall/router platform differences
- Where helpful, include concise tables.
- Use en-US.
- Optimize for a practical, copy-pasteable deliverable that can be implemented directly.

Start your research with these authoritative sources and cite them in your output:

Core schema / modeling:

- JSON Schema spec: https://json-schema.org/specification
- JSON Schema 2020-12: https://json-schema.org/draft/2020-12
- Pydantic models: https://pydantic.dev/docs/validation/latest/concepts/models/
- Pydantic JSON Schema: https://pydantic.dev/docs/validation/latest/concepts/json_schema/
- Pydantic JSON schema API: https://pydantic.dev/docs/validation/latest/api/pydantic/json_schema/

Envelope patterns:

- Kubernetes objects: https://kubernetes.io/docs/concepts/overview/working-with-objects/
- Backstage ADR002: https://backstage.io/docs/architecture-decisions/adrs-adr002/

NetBox:

- NetBox docs home: https://netboxlabs.com/docs/netbox/
- Planning / order of operations: https://netboxlabs.com/docs/netbox/getting-started/planning/
- REST API overview: https://netboxlabs.com/docs/netbox/integrations/rest-api/
- NetBox model overview: https://netboxlabs.com/docs/netbox/development/models/
- IPAM: https://netboxlabs.com/docs/netbox/features/ipam/
- VLAN management: https://netboxlabs.com/docs/netbox/features/vlan-management/
- Virtualization: https://netboxlabs.com/docs/netbox/features/virtualization/
- Virtual machines: https://netboxlabs.com/docs/netbox/models/virtualization/virtualmachine/
- VM interfaces: https://netboxlabs.com/docs/netbox/models/virtualization/vminterface/
- Application services: https://netboxlabs.com/docs/netbox/models/ipam/service/

Network modeling:

- RFC 7950 YANG 1.1: https://datatracker.ietf.org/doc/html/rfc7950
- OpenConfig models landing page: https://openconfig.net/projects/models/
- OpenConfig interfaces: https://openconfig.net/projects/models/schemadocs/yangdoc/openconfig-interfaces.html
- OpenConfig VLAN: https://openconfig.net/projects/models/schemadocs/yangdoc/openconfig-vlan.html

Containerlab:

- Topology definition: https://containerlab.dev/manual/topo-def-file/
- Networking model: https://containerlab.dev/manual/network/
- Graph command: https://containerlab.dev/cmd/graph/

OpenTofu / Proxmox:

- OpenTofu validate: https://opentofu.org/docs/cli/commands/validate/
- OpenTofu plan: https://opentofu.org/docs/cli/commands/plan/
- OpenTofu custom conditions: https://opentofu.org/docs/language/expressions/custom-conditions/
- BPG Proxmox provider docs home: https://bpg.sh/docs/
- BPG Proxmox provider repo: https://github.com/bpg/terraform-provider-proxmox
- OpenTofu provider index: https://search.opentofu.org/provider/bpg/proxmox/latest
- VM resource docs: https://search.opentofu.org/provider/bpg/proxmox/latest/docs/resources/virtual_environment_vm
- LXC resource docs: https://search.opentofu.org/provider/bpg/proxmox/latest/docs/resources/virtual_environment_container
- Cloud-init guide: https://search.opentofu.org/provider/bpg/proxmox/latest/docs/guides/cloud-init
- Clone VM guide: https://search.opentofu.org/provider/bpg/proxmox/latest/docs/guides/clone-vm

Implementation examples only:

- Docker Compose file reference: https://docs.docker.com/reference/compose-file/
- Docker Compose services reference: https://docs.docker.com/reference/compose-file/services/

Policy / guardrails:

- OPA policy language (Rego): https://openpolicyagent.org/docs/policy-language
- Conftest: https://www.conftest.dev/
- Checkov home: https://www.checkov.io/
- Checkov custom policies overview: https://www.checkov.io/3.Custom%20Policies/Custom%20Policies%20Overview.html
- Checkov YAML custom policies: https://www.checkov.io/3.Custom%20Policies/YAML%20Custom%20Policies.html
- Trivy misconfiguration scanning: https://trivy.dev/docs/latest/scanner/misconfiguration/
- Trivy custom checks with Rego: https://trivy.dev/docs/latest/tutorials/misconfiguration/custom-checks/
- Trivy custom checks overview: https://trivy.dev/docs/dev/docs/scanner/misconfiguration/custom/

Testing / analysis:

- Batfish home: https://batfish.org/
- Batfish example notebooks: https://batfish.readthedocs.io/en/latest/public_notebooks.html
- Batfish forwarding analysis: https://batfish.readthedocs.io/en/latest/notebooks/linked/introduction-to-forwarding-analysis.html
- Batfish forwarding change validation: https://batfish.readthedocs.io/en/latest/notebooks/linked/introduction-to-forwarding-change-validation.html
- Batfish failure-impact analysis: https://batfish.readthedocs.io/en/latest/notebooks/linked/analyzing-the-impact-of-failures-and-letting-loose-a-chaos-monkey.html

CI / Ansible linting:

- ansible-lint usage: https://docs.ansible.com/projects/lint/usage/

Now do the research and produce the complete deliverable.
```
