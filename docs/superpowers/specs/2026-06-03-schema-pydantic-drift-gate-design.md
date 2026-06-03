# Design — Schema↔Pydantic Drift Gate

- **Status:** Approved (design); ready for implementation planning
- **Date:** 2026-06-03
- **Roadmap item:** `PROJECT-STATUS-AND-ROADMAP.md` §6 Phase 1 #1 (drift gate); absorbs Phase 1 #3 (negative-example corpus)
- **Research backing:** [`docs/research/2026-06-02-json-schema-pydantic-drift-gate.md`](../../research/2026-06-02-json-schema-pydantic-drift-gate.md) (two passes: approach comparison + polyfactory viability)
- **SemVer impact:** MINOR (gate tooling + negative corpus) **+ PATCH** for two conformance fixes (D6:
  `Cidr`/`IpAddress` validators brought into agreement; no conformant document affected — verified)

---

## 1. Problem

`schemas/infra.schema.json` (hand-authored JSON Schema Draft 2020-12, **normative**) and
`python/infra_models.py` (Pydantic v2) are two **parallel, independently-authored** sources of
structural truth. Neither is generated from the other; their semantic equivalence is held only by
convention (documented in `CHANGELOG.md` and `PROJECT-STATUS-AND-ROADMAP.md` §3). Phase 2 generators
(NetBox / OpenTofu / Containerlab / Ansible emitters) consume the object model as ground truth; if the
two definitions of "valid" silently diverge, every generator inherits the divergence and produces
subtly wrong artifacts. The roadmap's own sequencing rationale (§6) makes this the prerequisite for
Phase 2.

This gate closes that hole: a CI check that **fails when the two validators would accept or reject
different documents**.

## 2. Goal & non-goals

**Goal.** Detect *structural* drift between the JSON Schema and the Pydantic model: shape, types,
required fields, object closedness, kind discrimination, and pattern/range-constrained primitives.

**Non-goals (explicitly out of scope, and the gate must say so in its own header + `ci/pipeline.md`):**

- **Cross-field graph constraints** — IP-in-prefix, referential integrity, composite-key uniqueness.
  These live only in Pydantic's `@model_validator`/`check_manifest` layer and are *not expressible* in
  JSON Schema. They are verified by the Pydantic graph layer (stage 3) and OPA (stage 4). The gate
  asserts structural parity, not graph parity. This residual gap is a deliberate, documented boundary.
- **Byte-for-byte schema equality.** The two encodings differ by design (named `$ref` primitives +
  `if/then` discrimination vs inlined primitives + discriminated `oneOf` with per-kind wrapper
  classes; 44 vs 65 `$defs`, 29 overlapping names). We compare *behavior* and a narrow slice of
  *structure*, never the full serialization.
- **`format` semantic validation.** See Decision D1.

## 3. Key decisions

### D1 — `format` is treated as annotation (FormatChecker OFF)

The gate's JSON Schema validator is constructed **without** a `format_checker`, matching the existing
`validate_examples.py` (`Draft202012Validator(SCHEMA)`) — so `format` keywords are annotation-only
repo-wide. Definitions in play:

- `IpAddress` `$def` = `{type: string, anyOf: [{format: ipv4}, {format: ipv6}]}` *(pre-D6; gains a
  `pattern` in D6 — see D6)* — shape carried only by `format`, which is **not enforced** when the
  checker is off.
- `Cidr` `$def` = `{type: string, anyOf: [{pattern: <ipv4-cidr>}, {pattern: <ipv6-cidr>}]}` —
  `pattern`-based, so it is enforced regardless of the checker.
- Pydantic types both as bare `Annotated[str, Field()]`
  ([`infra_models.py:110-111`](../../../python/infra_models.py#L110-L111)); their shape is enforced by
  **field-level** `@field_validator`s (`IpConfig.address`/`gateway`, `PrefixSpec.cidr`) that run during
  `DocumentAdapter.validate_python` — *not* in the graph layer.

Why the checker stays off: `hostname`/`uri` fields are lenient on **both** sides (no Pydantic
validator, `format` off), so enabling `FormatChecker` would reject strings Pydantic accepts —
manufacturing false drift. Keeping it off is also the established repo convention.

This decision is sound, but it exposed (and the quality review confirmed) two **real** IP-primitive
divergences that are *not* false drift and are reconciled in **D6** — not papered over by the
checker decision.

### D2 — Plain script, not a test framework

The gate ships as `_build/check_drift.py`, a plain script returning exit `0`/`1`, mirroring
`_build/validate_examples.py`. No pytest/unittest is introduced — consistent with the existing
validator pattern and the §7 `uv run python …` invocation style.

### D3 — Reuse existing validators, do not re-implement

- JSON Schema side: `Draft202012Validator(SCHEMA)` (format off), same as `validate_examples.py`.
- Pydantic side: `infra_models.DocumentAdapter.validate_python(raw)` for single documents; it raises
  `pydantic.ValidationError` on reject. Also reuse `KINDS`, `API_VERSION`, `emit_schema()`.

### D4 — Collect-all, not fail-fast

The gate accumulates *every* divergence across all components, prints one table, then exits 1 if any
row exists. One run shows the whole drift surface (better DX than first-failure abort).

### D5 — Negative corpus folded in (Phase 1 #3)

Component C2's `examples/invalid/` corpus *is* the roadmap's "negative-example corpus as tests." The
two roadmap items are one artifact viewed two ways; building the gate produces the corpus. The
corpus is single-sourced here, and PROJECT-STATUS-AND-ROADMAP.md is updated to record the merge.

### D6 — IP-primitive reconciliation (two conformance fixes shipped with the gate)

The design review empirically surfaced two real, opposite structural divergences on the IP primitives
(verified with both validators):

| Field | Example | JSON Schema | Pydantic | Direction |
| --- | --- | --- | --- | --- |
| `Cidr` (e.g. `PrefixSpec.cidr`) | `::1`, `10.0.0.5`, `::ffff:192.168.1.0/120` | **reject** (regex requires `/prefix`) | **accept** (`ip_network(strict=False)`) | Pydantic broader |
| `IpAddress` (e.g. `IpConfig.gateway`) | `not-an-ip` | **accept** (`format` annotation-only) | **reject** (`ip_address()`) | JSON Schema broader |

Both are fixed (not snapshotted) by bringing the looser side to the schema author's evident intent:

1. **`Cidr` → tighten Pydantic.** `_validate_cidr` ([`infra_models.py:100`](../../../python/infra_models.py#L100))
   must additionally require an explicit prefix and match the schema's CIDR shape (reuse the schema's
   two `Cidr` regexes, or require a `/` plus `ip_network(strict=False)`), so Pydantic stops accepting
   prefix-less / IPv4-mapped forms the normative schema already rejects.
2. **`IpAddress` → tighten the schema.** Replace the `IpAddress` `$def`'s
   `anyOf: [{format: ipv4}, {format: ipv6}]` with `anyOf: [{pattern: <ipv4>}, {pattern: <ipv6>}]`,
   reusing the `Cidr` `$def`'s address-portion patterns **without** the `/prefix` suffix (the IPv4
   octet-range pattern; the loose `^[0-9a-fA-F:]+$` IPv6 form). Dropping `format` is fine — it is inert
   with the checker off (D1). This makes `IpAddress` pattern-based and consistent with `Cidr`, and makes
   the JSON Schema enforce the IP shape its `format` only annotated, matching Pydantic's `ip_address()`.
   **Known edge (do not regress):** `ip_address("::ffff:192.168.0.1")` (IPv4-mapped IPv6) succeeds, but
   the loose hex-colon IPv6 pattern rejects embedded dots — a *new* micro-divergence. It is **out of
   corpus scope** for this fix (no example or consumer uses it); the implementor must confirm that at
   step 5 and add an IPv4-mapped alternative pattern only if a real document needs one. Perfect
   regex-equality with `ip_address()` is a non-goal; closing the `not-an-ip` class is the goal.

**Classification: conformance fix, PATCH — not a breaking change.** The normative JSON Schema already
required a CIDR prefix; `IpAddress`'s `format` already declared IP intent. No *conformant* document
(valid under **both** validators) is affected. **Interpretive choice, stated explicitly:** the CHANGELOG
policy table's "tighten a constraint so previously-valid docs now fail → MAJOR" rule reads "valid" here
as *conformant under both validators simultaneously* — the only state a downstream consumer can rely on
— grounding the call in the table's final bullet ("schema↔Pydantic divergence is a bug, not a version
event"). Under a per-validator reading of "valid," fix-2 would instead score MAJOR; we deliberately do
not use that reading. Verified: all `cidr:` values in `examples/` are proper
`/24`s, and `../network-infrastructure/` has no YAML using `Prefix`/`cidr`/`gateway`. Recorded under
"Fixed" in `CHANGELOG.md` (per its policy that schema↔Pydantic divergence "is a bug, not a version
event"); **no `apiVersion` bump**. Editing the normative `schemas/infra.schema.json` requires re-running
validation stages 1–4 and keeping Pydantic in sync (AGENTS.md authoring rules). Post-fix, `::1` and
`not-an-ip` become `both-reject` regression fixtures in C2.

## 4. Architecture

```
_build/check_drift.py            # the gate (plain script, exit 0/1)
examples/invalid/
    structural/                  # docs BOTH validators must reject  (C2)
        <case>.yaml
    graph/                       # docs only Pydantic rejects (graph layer); JSON Schema accepts
        <case>.yaml
```

**CI placement.** A new "contract drift gate" stage that runs **after** stage 4 (OPA) and **before**
the generate stages (5+) in `ci/pipeline.md` — the contract must be locked before anything consumes
it. Command form (matches §7):

```bash
uv run python _build/check_drift.py
```

**Data flow.**

```
canonical schema  ┐
Pydantic model    ┤→ check_drift.py ─ C1 ─ C2 ─ C4 ─ [C3?] → aggregate table → exit 0/1
YAML corpora      ┘
```

Each divergence row: `component | locus (file or kind) | json-schema verdict | pydantic verdict | detail`.

## 5. Components

Component labels (C1, C2, C3, C4) follow the research report so cross-references stay stable: **C3 is
the generative component, C4 the structural check.** They are presented and built in *dependency
order* (C1 → C2 → C4, then the spike-gated C3), which is why the numbering below is not sequential.

### C1 — Valid-corpus agreement (deterministic, no new deps)

- **Inputs:** `examples/kinds/*.yaml` (19) + `examples/manifests/*.yaml` (2), loaded with the same
  multi-document `safe_load_all` handling as `validate_examples.py`.
- **Assertion:** for each document, JSON-Schema-accepts **iff** Pydantic-accepts. A document accepted
  by one and rejected by the other is a drift row (report the rejecting side's first error).
- **Why:** stages 2 and 3 already run each validator independently; C1 asserts they *agree* on the
  same inputs — the cheapest, highest-baseline check.

### C2 — Invalid-corpus rejection (deterministic, no new deps; = Phase 1 #3)

- **Inputs:** new hand-authored corpus, ~20–30 files, each a *definitively* invalid document. Layout
  splits by what can catch it:
  - `examples/invalid/structural/` — **both** validators must reject.
  - `examples/invalid/graph/` — only Pydantic rejects (JSON Schema accepts by design; asserted
    Pydantic-only so the corpus documents the scope boundary rather than hiding it).
- **`structural/` categories** (target pattern/range primitives + envelope/closedness, *not* `format`
  fields, per D1):
  - unknown `kind` (outside the `Kind` enum)
  - missing a required envelope field (`apiVersion`/`kind`/`metadata`/`spec`)
  - extra/unknown property on a closed object (exercises `additionalProperties:false` ⇔ `extra='forbid'`)
  - kind↔spec mismatch (e.g. `kind: Site` carrying a `Vlan` spec)
  - malformed pattern primitive: bad MAC, bad slug, bad `Duration`, bad `apiVersion`
  - **D6 regression fixtures:** `PrefixSpec.cidr: "::1"` (prefix-less) and `IpConfig.gateway:
    "not-an-ip"` — both-reject *after* the D6 fixes; they guard against either fix regressing
  - out-of-range integer: port (1–65535), VLAN id (1–4094), VM id (100–999999999)
  - wrong scalar type (string where integer required)
- **`graph/` categories:** IP outside its declared prefix; dangling `ObjectRef`; duplicate composite
  key. (JSON Schema cannot see these; Pydantic `check_manifest`/graph rejects them.)
- **Assertion:** every `structural/` doc rejected by **both**; every `graph/` doc rejected by
  Pydantic. If a `structural/` doc is *accepted* by either side, that side is too permissive → drift
  (name which side).
- **Self-evidence:** because C2 fixtures are definitively invalid, C2 also proves the gate can *see*
  rejection divergence — this replaces the dropped `--selftest` mode (see §7).
- **Coverage caveat (honest bound).** The deterministic core (C1+C2+C4) catches a structural
  divergence only where a *curated* fixture or the valid corpus exercises it. It does **not**
  exhaustively detect *new, unforeseen* field-level divergences (in either direction) — that is C3's
  job (generative). With C3 deferred, the two known divergences are reconciled (D6) and guarded by
  regression fixtures, but a *future* field that drifts without a hand-authored fixture would pass
  until C3 lands or someone adds a fixture. This is the deterministic core's residual bound, stated
  rather than hidden. (C3 only generates from Pydantic, so even C3 primarily catches the
  Pydantic-broader direction; the schema-broader direction relies on curated fixtures — see §10.)

### C4 — Structural contract check (~50 LOC, deterministic, no new deps)

Compares the two schemas at a narrow, stable slice — no full normalization, so it does not try to
reconcile `if/then` vs discriminated `oneOf` mechanically (research showed that is undecidable in the
general case and brittle to new kinds). Checks:

1. **Kind-set parity:** canonical `Kind` enum  ==  Pydantic discriminated-union literals  ==  `KINDS`
   tuple  ==  `{yaml.safe_load(f.read_text())['kind'] for f in (ROOT / 'examples/kinds').glob('*.yaml')}`.
   (File stems are kebab-case and do not match PascalCase Kind values; read the `kind:` field from
   each YAML instead. Catches a kind added to one side only.)
2. **Per-kind required-field parity:** for each kind, the canonical `<Kind>Spec` `$def` `required`
   list (after resolving the `if kind==X then spec:$ref` mapping) == the Pydantic `<Kind>Spec`
   required fields (fields without defaults), compared by alias.
3. **Closedness parity:** canonical spec `additionalProperties:false` ⇔ Pydantic `extra='forbid'`.
   **`Labels` is special-cased** as a known-open free-form `dict[str,str]` map (it is intentionally
   `additionalProperties:<string-schema>`, not `false`); it must be open on both sides, and the gate
   asserts that rather than flagging it.

### C3 — Generative positive corpus (SPIKE-GATED; adds `polyfactory>=2.16.1` dev dep)

- **Mechanism:** one `polyfactory` `ModelFactory` per kind (over the `*Spec`/Object classes).
  - `__random_seed__ = 1729` (a fixed integer) for reproducible CI — seeds both `random` and Faker.
  - `infra_models.py` uses `from __future__ import annotations`, so all type annotations are
    deferred strings at runtime. `polyfactory` calls `model.model_rebuild()` automatically, which
    resolves them. No explicit `__forward_references__` dict is expected to be needed, but the
    spike should confirm this for any model that uses forward-referenced types.
  - Use `ModelFactory.coverage()` to emit one instance per `Literal`/`Union` branch, plus a small
    fixed number of seeded `build()` instances for volume.
  - `build()` runs full `model_validate()` by default — **never** `factory_use_construct=True` — so a
    mis-generated value fails loudly at build time rather than producing a false drift report.
  - Each generated model → `model.model_dump(mode="json", by_alias=True)` (alias + JSON mode so it
    matches the canonical schema's property names) → `Draft202012Validator` (format off). A generated
    instance the JSON Schema *rejects* is drift (Pydantic broader than the schema).
- **Known footgun & fix:** when a field has both an anchored `pattern` and a `max_length` shorter
  than the pattern's minimum match length, `polyfactory` generates a regex-matching string and then
  truncates it, breaking the anchored match. Among the four constrained primitives in this schema:
  `Mac`, `Duration`, and `ApiVersion` have no `max_length` (no truncation risk); `Slug` has
  `max_length=63` equal to the pattern's own maximum (truncation is a no-op). The actual number of
  overrides needed is empirically unknown until the spike — the estimate of 0–8 is conservative.
  Fix per affected field: a one-line factory override supplying 3–5 curated valid values
  (or `Field(examples=[...])` + `__use_examples__`).
- **Spike accept/defer criterion:** include C3 in v1 **iff** the custom-provider overrides needed stay
  ≤ ~8 fields and no structural generation breakage appears. Otherwise defer C3, document it as a
  fast-follow with this spec's findings, and ship the deterministic core (C1+C2+C4) alone — that core
  already lands a working gate and the negative corpus.

## 6. Dependencies & toolchain

- C1/C2/C4: stdlib + already-pinned `jsonschema`, `pydantic`, `PyYAML`. **No new dependency.**
- C3 (only if the spike passes): add exact-pinned `polyfactory>=2.16.1` to `[dependency-groups] dev`
  in `pyproject.toml`; relock `uv.lock` (`uv lock`). Pin exactly, per repo convention.

## 7. Error handling, reporting, and self-evidence

- **Reporting:** collect all divergence rows; print a single table; exit 1 if non-empty, else 0.
- **No silent no-op:** the gate must fail if it finds *zero* kinds or *zero* corpus files (a likely
  sign of a path bug) rather than reporting a vacuous pass.
- **Self-evidence over `--selftest`:** the shipped `--selftest` flag is dropped (YAGNI). Detection
  ability is proven by construction: when the gate is first run (C4+C1+C2 built, **before** the D6
  fixes), it flags the two real `Cidr`/`IpAddress` divergences. That is recorded, real-world evidence
  the gate detects drift — stronger than a synthetic injected mismatch — and the D6 fixes then turn it
  green. C2's definitively-invalid corpus continues to exercise rejection divergence on every run.

## 8. Documentation & versioning impact

- **Files changed by the D6 fixes** (re-run validation stages 1–4 after, per AGENTS.md):
  `python/infra_models.py` (`_validate_cidr` tightened) and `schemas/infra.schema.json` (`IpAddress`
  gains a `pattern`). Keep the two schemas semantically in sync in the same commit.
- `CHANGELOG.md`: **Added** (MINOR) — drift gate + negative corpus; **Fixed** (PATCH) — D6
  `Cidr`/`IpAddress` conformance (schema↔Pydantic divergence is a bug, not a version event; no
  `apiVersion` bump).
- `PROJECT-STATUS-AND-ROADMAP.md`: §6 Phase 1 #1 → done; #3 marked folded into #1; §8 post-build
  change-log entry (note the D6 fixes); §4/§7 updated if C3 ships (new dep, new command).
- `ci/pipeline.md`: add the "contract drift gate" stage after stage 4.
- `AGENTS.md`: add the drift-gate command to the "Validation — Run in Order" table.

## 9. Build sequence

1. **C4** (kind-set + required-field + closedness parity) — smallest, proves the harness wiring.
2. **C1** (valid-corpus agreement) — reuses both validators on existing examples.
3. **C2** (`examples/invalid/` corpus + assertions) — lands the gate's highest-signal check and the
   Phase 1 #3 negative corpus. **Author the two D6 regression fixtures here** (`PrefixSpec.cidr: "::1"`
   and `IpConfig.gateway: "not-an-ip"`, both in `structural/`, asserted both-reject). They are what
   make the divergences visible at step 4 — without them C1's all-valid corpus produces zero rows.
4. **Run the gate — expect RED.** Pre-fix, C2 flags Pydantic as too-permissive on `::1` and JSON Schema
   as too-permissive on `not-an-ip` → two drift rows → exit 1. This is the real proof-of-detection (§7).
5. **D6 conformance fixes (code only)** — tighten `_validate_cidr`; add the `IpAddress` `pattern` per
   D6 fix-2's rule (no new fixtures here — they already exist from step 3). Re-run validation stages
   1–4; both fixtures now reject on both sides → gate green.
6. **C3 spike** — implement factories + overrides; apply the §5 accept/defer criterion.
7. **Docs/CHANGELOG/CI** — record the change (incl. the D6 "Fixed" entry); wire the CI stage.

Steps 1–5 ship a complete, green gate plus the reconciled contract even if step 6 (C3) defers.

## 10. Open questions (empirical, resolved during implementation)

| # | Question | Resolved by |
|---|----------|-------------|
| 1 | Exact count of anchored-`pattern`+`max_length` fields needing a C3 override | The C3 spike (step 6) |
| 2 | Do any `*Spec` numeric bounds (VLAN/VM id ranges) differ between schema and Pydantic? | Surfaces behaviorally in C1/C2; C4 may add a bounds check if a gap appears |
| 3 | Does `model_dump(mode="json", by_alias=True)` round-trip every kind cleanly into schema-valid JSON? | The C3 spike |
| 4 | Detection of *future* schema-broader field divergences (C3 generates from Pydantic only, so it catches mainly the Pydantic-broader direction) | Accepted residual of the deterministic core; revisit if a generate-from-schema path becomes viable |
| 5 | Confirm `../network-infrastructure/` has no *non-YAML* reliance on `Cidr`/`IpAddress` leniency before applying D6 | Re-check at the start of D6 implementation (step 5) |

## 11. References

- Research report: [`docs/research/2026-06-02-json-schema-pydantic-drift-gate.md`](../../research/2026-06-02-json-schema-pydantic-drift-gate.md)
- Existing validator (style + format-off precedent): [`_build/validate_examples.py`](../../../_build/validate_examples.py)
- Pydantic reuse handles: [`python/infra_models.py`](../../../python/infra_models.py) — `DocumentAdapter`, `KINDS`, `emit_schema()`, `check_manifest`
- Roadmap: [`docs/PROJECT-STATUS-AND-ROADMAP.md`](../../PROJECT-STATUS-AND-ROADMAP.md) §6
