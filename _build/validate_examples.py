#!/usr/bin/env python3
"""Validate every example YAML against schemas/infra.schema.json.

Handles single-object files, InfraManifest bundles, and multi-document YAML
streams (split on '---'). JSON Schema validates one document at a time;
stream-splitting is a harness responsibility, documented in the README.
"""
import sys
import json
import pathlib
import yaml
from jsonschema import Draft202012Validator

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "infra.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


def validate_doc(doc, label):
    errors = sorted(VALIDATOR.iter_errors(doc), key=lambda e: list(e.path))
    if errors:
        print(f"FAIL  {label}")
        for e in errors[:6]:
            loc = "/".join(str(p) for p in e.path) or "<root>"
            print(f"      [{loc}] {e.message}")
        return False
    print(f"ok    {label}")
    return True


def main():
    ok = True
    # Only the hand-authored desired-state examples are validated against the
    # infra schema. Generated artifacts under examples/ (Containerlab topology,
    # OpenTofu HCL) are NOT desired-state objects and are validated by their own
    # tools (containerlab/tofu), so they are excluded here.
    files = sorted(
        f
        for sub in ("kinds", "manifests")
        for f in (ROOT / "examples" / sub).rglob("*.yaml")
    )
    for f in files:
        rel = f.relative_to(ROOT)
        docs = list(yaml.safe_load_all(f.read_text()))
        docs = [d for d in docs if d is not None]
        if len(docs) == 1:
            ok &= validate_doc(docs[0], str(rel))
        else:
            for i, d in enumerate(docs):
                ok &= validate_doc(d, f"{rel}#doc{i}")
    print("\nRESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
