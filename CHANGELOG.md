# Changelog

All notable changes to the Luminous3D desired-state infrastructure model are recorded here. Format follows Keep a Changelog; the project follows Semantic Versioning.

## Versioning policy

Two coupled version tracks:

1. **`apiVersion`** (in every YAML document, e.g. `infra.luminous3d.example/v1alpha1`) — the stability contract of the object model. Maturity ladder mirrors Kubernetes: `vNalpha1` → `vNbeta1` → `vN`.
2. **Repo/schema SemVer** (`MAJOR.MINOR.PATCH`, in this file and any release tag) — the version of the schema pack as shipped.

Change classification:

| Change | apiVersion impact | SemVer impact |
| --- | --- | --- |
| Remove/rename an envelope or spec field; tighten an existing constraint so previously-valid docs now fail; change a reference scheme | bump apiVersion track (e.g. `v1alpha1`→`v1beta1`); provide migration notes | MAJOR |
| Add a new kind; add an optional field; add a new policy that only warns | same apiVersion | MINOR |
| Add a `deny` policy that rejects previously-accepted documents | same apiVersion (data shape unchanged) but it is a behavior break | MAJOR (policy layer) |
| Loosen a constraint (accept more) | same apiVersion | MINOR |
| Docs, comments, example fixes, non-normative clarifications | same apiVersion | PATCH |

Rules of thumb:

- While on an `alpha` apiVersion, breaking changes are permitted between MINOR releases but must still be listed under a "Changed (breaking)" heading here.
- Promote `alpha` → `beta` only once the kind set and reference scheme are considered stable for external generators to build against.
- The hand-authored `schemas/infra.schema.json` is the normative artifact. The Pydantic-derived schema (`infra_models.py --emit-schema`) is a parallel validator and is allowed to differ in non-semantic presentation (descriptions, `$defs` naming); any _semantic_ divergence is a bug, not a version event.

## [Unreleased]

_Nothing yet._

## [0.1.0] — 2026-06-02

Initial tested baseline. `apiVersion: infra.luminous3d.example/v1alpha1`.

### Added

- **JSON Schema** (`schemas/infra.schema.json`, Draft 2020-12): shared envelope (`apiVersion`/`kind`/`metadata`/`spec`), 19 object kinds plus the `InfraManifest` bundle, closed objects throughout, per-kind `if/then` discrimination, reusable `$defs` (ObjectRef, SecretRefInline, ExposureDecision, enums). Root `oneOf[Object, Bundle]`.
- **Pydantic v2 models** (`python/infra_models.py`): strict base (`extra=forbid`), one `*Spec` per kind, discriminated `AnyObject` union, `InfraManifest`, a graph layer (`check_manifest`: unique composite keys, referential integrity, IP-in-prefix), and a CLI (`--check`, `--merge`, `--emit-schema`).
- **Examples**: one minimal valid document per kind (19 files); two manifests — `site-home.yaml` (single-site closed world) and `multi-site-failover.yaml` (multi-site + failover + FailureScenario).
- **Guardrail policies** (`policies/opa/`): exposure (public service needs an approved ExposureDecision), backup (critical service needs a resolvable BackupClass with a restore target), privileged (privileged LXC needs an approval annotation), zone_isolation (management must not join guest/IoT), ip_prefix (guest IPv4 within a declared Prefix); shared `lib/objects.rego`; 15 unit tests in `policy_test.rego`; `conftest/` invocation notes.
- **Mappings & generator rules**: NetBox seed/import guide (two-pass seed, bulk POST, concrete payloads, version quirks); bpg/proxmox HCL mapping guide (VM/LXC field asymmetries, cloud-init/secret adaptation points); Containerlab topology rules.
- **Worked generated examples**: `examples/opentofu/proxmox-example.tf` (1 VM + 1 LXC); `examples/containerlab/generated-topology.clab.yaml` (router-on-a-stick home projection).
- **CI** (`ci/pipeline.md`): 9 ordered stages with commands, each tagged `[verified]` or `[described]`; Checkov/Trivy scope guidance (they scan generated artifacts, not the abstract model).
- **README** and this **CHANGELOG**; `.yamllint.yml` house style.

### Validation

Verified in-environment: `yamllint -s` (clean); JSON Schema (21 docs pass); Pydantic `--check` (all kinds + both manifests pass; `--merge` flags cross-manifest duplicate keys as designed); `conftest verify` (15/15); `conftest test --combine` per manifest (9/9 each); `tofu init && validate` on the example HCL (success, bpg/proxmox 0.108.0).

Described, not executed here (need Docker, live endpoints, or device configs): Containerlab deploy, Batfish, Checkov, Trivy, ansible-lint, live NetBox seed, `tofu plan` against a real Proxmox API.

### Known limitations

- Generator executables are not yet implemented; only mapping rules + one worked example per target ship in this baseline.
- NetBox cannot represent NetworkZone, ServiceDependency, firewall intent, an LXC guest type, or BackupClass natively; these project to custom fields/tags/labels or are intentionally dropped.
- Containerlab has no native OPNsense kind; the firewall projects to a `linux`/FRR node with the adaptation recorded in labels.
- Conftest must be invoked once per closed-world unit; pooling independent manifests that re-declare shared fixtures is unsupported by design.

[Unreleased]: https://l3digital.example/infra-schema/compare/v0.1.0...HEAD
[0.1.0]: https://l3digital.example/infra-schema/releases/tag/v0.1.0
