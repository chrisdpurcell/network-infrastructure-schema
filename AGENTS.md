# AGENTS.md

## Purpose

Desired-state infrastructure schema for the Luminous3D homelab. 19 Kubernetes-style object kinds (sites, zones, VLANs, prefixes, devices, interfaces, Proxmox VMs/LXC, services, firewall policies, backup classes, secrets, monitoring, failure scenarios). Downstream artifacts (NetBox, OpenTofu HCL, Containerlab, Ansible) are _generated_ from validated YAML — never hand-authored.

## Related Repositories

**network-infrastructure** consumes this schema. Breaking schema changes require migration planning there before committing here.

- [network-infrastructure](../network-infrastructure/)
- <https://github.com/chrisdpurcell/network-infrastructure>

## Directory Layout

| Path | Role |
| --- | --- |
| `schemas/infra.schema.json` | **Normative** — hand-authored JSON Schema Draft 2020-12. Do not overwrite with `--emit-schema`. |
| `python/infra_models.py` | Pydantic v2 — mirrors JSON Schema, adds graph checks (referential integrity, IP-in-prefix, composite-key uniqueness). |
| `policies/opa/` | Conftest/OPA guardrails: exposure, backup, privileged, zone isolation, IP-in-prefix. `policy_test.rego` has 15 tests. |
| `examples/kinds/` | One minimal valid YAML per kind (19 files). Schema fixtures — not live state. |
| `examples/manifests/` | Closed-world manifests for integration tests. |
| `examples/opentofu/` | Generated HCL example — do not edit by hand. |
| `examples/containerlab/` | Generated topology example — do not edit by hand. |
| `generators/` | Mapping guides for downstream targets. Not executable code. |
| `_build/` | `build_schema.py`, `validate_examples.py`. |
| `ci/pipeline.md` | 9-stage CI spec. Read before proposing new validation steps. |
| `backups/` | Archived schema releases. Do not edit. |
| `live/` | _(not yet created)_ Real infrastructure state documents go here. |

## Validation — Run in Order

Each stage gates the next. Do not skip ahead.

| # | Stage | Command |
| --- | --- | --- |
| 1 | YAML lint | `yamllint -s -c .yamllint.yml examples/` |
| 2 | JSON Schema | `python3 _build/validate_examples.py` |
| 3 | Pydantic + graph | `python3 python/infra_models.py --merge --check <files>` |
| 4 | OPA guardrails | `conftest verify -p policies/opa` then `conftest test --combine -p policies/opa <files>` |
| 5+ | Generate → scan → tofu → ansible → netsim | See `ci/pipeline.md` |

## Authoring Rules

### Schema changes

- JSON Schema and Pydantic models must stay semantically in sync. Add a new kind to _both_ in the same commit.
- `closedness` (`additionalProperties: false`) is intentional — add the field explicitly, never relax it.
- Re-run stages 1–4 and confirm clean before committing any schema change.

### Adding a new kind

1. Add kind to `KINDS` tuple in `infra_models.py` and add a `*Spec` class.
2. Add the `if/then` discriminator block and `$defs` entry in `schemas/infra.schema.json`.
3. Add `examples/kinds/<kind-slug>.yaml`.
4. Run stages 1–4.
5. Record in `CHANGELOG.md` as a MINOR bump.

### Breaking changes (remove/rename field, tighten constraint, change reference scheme)

1. Check `../network-infrastructure/` for all uses of the affected kind/field.
2. Add a "Changed (breaking)" entry in `CHANGELOG.md`.
3. Bump `apiVersion` track (e.g. `v1alpha1` → `v1beta1`) and update `API_VERSION` in `infra_models.py`.
4. MAJOR SemVer bump in `CHANGELOG.md`.

### Policies

- Every new `deny` rule needs a test case in `policy_test.rego`.
- A `deny` rule that rejects currently-valid examples is a breaking change (MAJOR bump + update examples).

## Versioning

Two coupled tracks — full policy in `CHANGELOG.md`.

- **`apiVersion`** — stability contract of the object model (e.g. `infra.luminous3d.example/v1alpha1`).
- **Repo SemVer** — version of the schema pack as shipped.

Current: `apiVersion: infra.luminous3d.example/v1alpha1`, repo `v0.1.0`.

On `alpha`: breaking changes between MINOR releases are permitted but must appear under "Changed (breaking)" in `CHANGELOG.md`.

## Constraints

- **No v3 handoff, no external file-management conventions.** Do not create, delete, or reorganize files per any external system convention.
- Never commit secrets or plaintext credentials — use `SecretRef`.
- `examples/opentofu/` and `examples/containerlab/` are generated artifacts — do not edit by hand.
