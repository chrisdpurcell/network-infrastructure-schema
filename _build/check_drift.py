#!/usr/bin/env python3
"""Schema<->Pydantic drift gate.

Fails (exit 1) when schemas/infra.schema.json (normative) and
python/infra_models.py would accept or reject different documents. Tests
STRUCTURAL equivalence only: shape, types, required fields, closedness,
kind discrimination, pattern/range primitives. Cross-field graph checks
(IP-in-prefix, referential integrity, composite-key uniqueness) are OUT OF
SCOPE here -- they are Pydantic-@model_validator-only and are covered by
infra_models --check (stage 3) and OPA (stage 4).

format is annotation-only: the JSON Schema validator is built WITHOUT a
format_checker, matching validate_examples.py. Do not add one (spec D1).

See docs/superpowers/specs/2026-06-03-schema-pydantic-drift-gate-design.md.
"""
import json
import pathlib
import sys

import yaml
from jsonschema import Draft202012Validator

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
import infra_models as m  # noqa: E402

SCHEMA = json.loads((ROOT / "schemas" / "infra.schema.json").read_text())
JS = Draft202012Validator(SCHEMA)  # format_checker intentionally omitted (D1)

# Divergence accumulator: rows of (component, locus, js, py, detail).
DRIFT: list[tuple] = []


def record(component, locus, js, py, detail=""):
    def v(x):
        return "-" if x is None else ("accept" if x else "reject")
    DRIFT.append((component, locus, v(js), v(py), detail))


def kind_to_spec_name() -> dict:
    """Map each kind to its <Kind>Spec $def name via the Object if/then blocks."""
    out = {}
    for blk in SCHEMA["$defs"]["Object"]["allOf"]:
        const = blk["if"]["properties"]["kind"]["const"]
        out[const] = blk["then"]["properties"]["spec"]["$ref"].rsplit("/", 1)[-1]
    return out


def load_docs(path: pathlib.Path) -> list:
    return [d for d in yaml.safe_load_all(path.read_text()) if d is not None]


def js_ok(doc) -> tuple[bool, str]:
    errs = sorted(JS.iter_errors(doc), key=lambda e: list(e.path))
    if errs:
        loc = "/".join(str(p) for p in errs[0].path) or "<root>"
        return False, f"[{loc}] {errs[0].message}"
    return True, ""


def py_ok(doc) -> tuple[bool, str]:
    """Structural (field-level) Pydantic validation -- NOT graph checks."""
    try:
        m.DocumentAdapter.validate_python(doc)
        return True, ""
    except Exception as e:  # pydantic.ValidationError
        return False, str(e).splitlines()[0]


def c4_structural_contract():
    pyd = m.emit_schema()
    canon_kinds = set(SCHEMA["$defs"]["Kind"]["enum"])
    pyd_kinds = set(m.KINDS)
    example_kinds = set()
    for f in (ROOT / "examples" / "kinds").glob("*.yaml"):
        doc = yaml.safe_load(f.read_text())
        if doc is None or "kind" not in doc:
            print(f"FATAL: {f.relative_to(ROOT)} has no 'kind' key")
            sys.exit(2)
        example_kinds.add(doc["kind"])
    if not (canon_kinds == pyd_kinds == example_kinds):
        record("C4", "kind-set", None, None,  # js/py N/A for structural checks
                f"schema-only={sorted(canon_kinds - pyd_kinds)} "
                f"pydantic-only={sorted(pyd_kinds - canon_kinds)} "
                f"missing-example={sorted(canon_kinds - example_kinds)}")

    for kind, spec in kind_to_spec_name().items():
        cdef = SCHEMA["$defs"].get(spec, {})
        pdef = pyd["$defs"].get(spec, {})
        creq, preq = set(cdef.get("required", [])), set(pdef.get("required", []))
        if creq != preq:
            record("C4", f"{kind}:{spec}.required", None, None,  # js/py N/A for structural checks
                    f"schema-only={sorted(creq - preq)} pydantic-only={sorted(preq - creq)}")
        cclosed = cdef.get("additionalProperties") is False
        pclosed = pdef.get("additionalProperties") is False
        if cclosed != pclosed:
            record("C4", f"{kind}:{spec}.closed", None, None,  # js/py N/A for structural checks
                    f"schema_closed={cclosed} pydantic_closed={pclosed}")


def c1_valid_corpus_agreement():
    files = sorted(
        f for sub in ("kinds", "manifests")
        for f in (ROOT / "examples" / sub).rglob("*.yaml")
    )
    for f in files:
        docs = load_docs(f)
        for i, doc in enumerate(docs):
            label = str(f.relative_to(ROOT)) + ("" if len(docs) == 1 else f"#doc{i}")
            j, jd = js_ok(doc)
            p, pd = py_ok(doc)
            if j != p:
                record("C1", label, j, p, jd if not j else pd)


def report_and_exit():
    n_kinds = len(SCHEMA["$defs"]["Kind"]["enum"])
    n_examples = len(list((ROOT / "examples" / "kinds").glob("*.yaml")))
    if n_kinds == 0 or n_examples == 0:
        print("FATAL: found zero kinds or zero examples -- path bug, not a pass.")
        sys.exit(2)
    if DRIFT:
        print(f"DRIFT DETECTED ({len(DRIFT)} row(s)):\n")
        print(f"{'comp':<5} {'locus':<50} {'json':<7} {'pyd':<7} detail")
        print("-" * 94)
        for c, locus, js, py, detail in DRIFT:
            print(f"{c:<5} {locus:<50} {js:<7} {py:<7} {detail}")
        sys.exit(1)
    print(f"OK -- schema and Pydantic agree ({n_kinds} kinds, {n_examples} examples).")
    sys.exit(0)


def main():
    c4_structural_contract()
    c1_valid_corpus_agreement()
    report_and_exit()


if __name__ == "__main__":
    main()
