#!/usr/bin/env python3
"""validate.py — structural audit + standards check.

Runs ezdxf's audit and compares the drawing's layers against
standards/layers.yml. Reports anything that doesn't conform.

Usage:
    python scripts/validate.py drawings/site.dxf
    python scripts/validate.py drawings/site.dxf --fix --out drawings/site.fixed.dxf
    python scripts/validate.py drawings/site.dxf --standards standards/layers.yml
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from _lib import dump_json, load


def load_standards(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        print(
            "warning: PyYAML not installed; standards check skipped. "
            "pip install pyyaml",
            flush=True,
        )
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def check_standards(doc, standards: dict) -> dict:
    """Compare doc's layers against the standards spec.

    Standards schema (see standards/layers.yml):
      name_pattern: regex that any layer name must match
      required_layers: list of layers that must be present
      forbidden_layers: list of exact names that must not be present
      layer_specs:      list of {pattern, color, linetype} expectations
    """
    if not standards:
        return {"checked": False, "reason": "no standards file or empty"}

    issues = []
    layer_names = [l.dxf.name for l in doc.layers]

    # Global naming pattern
    np = standards.get("name_pattern")
    if np:
        rx = re.compile(np)
        for name in layer_names:
            # skip system layers
            if name in ("0", "Defpoints"):
                continue
            if not rx.match(name):
                issues.append(
                    {
                        "kind": "name_pattern",
                        "layer": name,
                        "message": f"does not match {np}",
                    }
                )

    # Required layers
    for req in standards.get("required_layers", []) or []:
        if str(req) not in layer_names:
            issues.append(
                {
                    "kind": "missing_required",
                    "layer": str(req),
                    "message": "required layer not present",
                }
            )

    # Forbidden layers
    for bad in standards.get("forbidden_layers", []) or []:
        if str(bad) in layer_names:
            issues.append(
                {
                    "kind": "forbidden",
                    "layer": str(bad),
                    "message": "forbidden layer is present",
                }
            )

    # Per-layer specs
    specs = standards.get("layer_specs", []) or []
    by_name = {l.dxf.name: l for l in doc.layers}
    for spec in specs:
        pat = spec.get("pattern")
        if not pat:
            continue
        rx = re.compile(pat)
        for name, layer in by_name.items():
            if not rx.match(name):
                continue
            if "color" in spec and int(layer.dxf.color) != int(spec["color"]):
                issues.append(
                    {
                        "kind": "wrong_color",
                        "layer": name,
                        "expected": spec["color"],
                        "actual": int(layer.dxf.color),
                    }
                )
            if "linetype" in spec and str(layer.dxf.linetype) != str(
                spec["linetype"]
            ):
                issues.append(
                    {
                        "kind": "wrong_linetype",
                        "layer": name,
                        "expected": spec["linetype"],
                        "actual": str(layer.dxf.linetype),
                    }
                )

    return {
        "checked": True,
        "issue_count": len(issues),
        "issues": issues,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file", type=Path)
    ap.add_argument(
        "--standards",
        type=Path,
        default=Path(__file__).parent.parent / "standards" / "layers.yml",
    )
    ap.add_argument(
        "--fix",
        action="store_true",
        help="save a recovered DXF after audit (requires --out)",
    )
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    doc, auditor = load(args.file, verbose=False)
    standards = load_standards(args.standards)
    standards_result = check_standards(doc, standards)

    audit_result = {
        "errors": [str(e) for e in auditor.errors][:50],
        "error_count": len(auditor.errors),
        "fixes_applied": len(auditor.fixes),
        "has_errors": bool(auditor.has_errors),
    }

    if args.fix:
        if not args.out:
            print("error: --fix requires --out", flush=True)
            raise SystemExit(2)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        doc.saveas(args.out)
        audit_result["fixed_file"] = str(args.out)

    out = {
        "file": str(args.file),
        "audit": audit_result,
        "standards_check": standards_result,
    }
    dump_json(out)


if __name__ == "__main__":
    main()
