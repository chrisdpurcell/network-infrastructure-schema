# Conftest / OPA guardrail policies

These policies enforce the cross-object and governance rules that JSON Schema
and the Pydantic structural layer cannot express. They are written in Rego
(OPA v1 syntax, `import rego.v1`) and executed with
[Conftest](https://www.conftest.dev/).

## Policy catalog

| File | Rule(s) | Enforces |
|------|---------|----------|
| `../opa/exposure.rego` | public service needs approval | A `Service` at `exposure.level: public` must set `approved: true` with a non-empty `approvedBy` and `reason`. |
| `../opa/backup.rego` | critical service backup | A `Service` with `criticality: critical` must reference a `BackupClass`, that reference must resolve, and the `BackupClass` must define a `restoreTarget`. |
| `../opa/privileged.rego` | privileged container approval | An `LxcContainer` with `unprivileged: false` must carry annotation `infra.luminous3d.example/privileged-approved: "true"`. |
| `../opa/zone_isolation.rego` | management isolation | No declared zone pair (from `FirewallPolicy` or `AllowedFlow`) may join a `management`-trust zone with a `guest`- or `iot`-trust zone. |
| `../opa/ip_prefix.rego` | IP within prefix | Every static guest IPv4 (VM/LXC NIC) must fall inside a declared `Prefix.cidr`. |
| `../opa/lib/objects.rego` | (library) | Normalizes the `--combine` input + `InfraManifest` bundles into a flat object set; provides `resolve()` for reference following. |

## Why `--combine` is mandatory

Conftest evaluates one YAML document at a time unless `--combine` is passed.
Almost every rule here is cross-object: a `Service` points at a `BackupClass`
defined in another file; a guest IP must be checked against `Prefix` objects
declared elsewhere. `--combine` makes `input` a single array of
`{path, contents}` entries spanning every file, which the shared library
flattens into the `objects` set. Running without `--combine` would silently
pass cross-object rules because the siblings would not be visible.

## Running

Policy enforcement against authored desired state (run from repo root):

```bash
conftest test --combine -p policies/opa \
  examples/manifests/site-home.yaml \
  examples/manifests/multi-site-failover.yaml
```

Whole-repo enforcement once a `live/` tree exists:

```bash
conftest test --combine -p policies/opa $(find live -name '*.yaml')
```

Unit tests for the policies themselves (no fixtures needed; inputs are inline):

```bash
conftest verify -p policies/opa
```

## Exit codes

`conftest test` exits non-zero on any `deny`, which is what gates CI. `deny` is
used throughout (not `warn`) because every rule here is a hard requirement;
promote a rule to `warn` only if you want it advisory.

## Adaptation points

- The privileged-approval annotation key is a convention defined in
  `privileged.rego`; change it there if your governance uses a different key.
- `zone_isolation.rego` evaluates **declared** zone pairs only. Emergent
  reachability (e.g. an IoT device reaching the management plane through a
  multi-hop service path) is the job of the Batfish reachability tests in CI,
  not a static policy. See `ci/pipeline.md`.
