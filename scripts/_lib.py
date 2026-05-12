"""Shared helpers for dxf-civil scripts.

Keep this small. Add a helper only when 2+ scripts need it.
"""
from __future__ import annotations

import fnmatch
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable

import ezdxf
from ezdxf import recover
from ezdxf.document import Drawing


# AutoCAD $INSUNITS code → human label
INSUNITS = {
    0: "unspecified",
    1: "inches",
    2: "feet",
    3: "miles",
    4: "millimeters",
    5: "centimeters",
    6: "meters",
    7: "kilometers",
    8: "microinches",
    9: "mils",
    10: "yards",
    11: "angstroms",
    12: "nanometers",
    13: "microns",
    14: "decimeters",
    15: "decameters",
    16: "hectometers",
    17: "gigameters",
    18: "astronomical units",
    19: "light years",
    20: "parsecs",
    21: "US survey feet",
}


def load(path: str | Path, *, verbose: bool = False) -> tuple[Drawing, Any]:
    """Load a DXF file with structural recovery.

    Returns (doc, auditor). Always use this instead of ezdxf.readfile().
    """
    p = Path(path)
    if not p.exists():
        die(f"file not found: {p}")
    if p.suffix.lower() == ".dwg":
        die(
            "DWG files are not supported. Convert to DXF first using AutoCAD's "
            "DXFOUT command or the free ODA File Converter."
        )
    try:
        doc, auditor = recover.readfile(str(p))
    except IOError as e:
        die(f"could not read {p}: {e}")
    except ezdxf.DXFStructureError as e:
        die(f"DXF structure error in {p}: {e}")
    if verbose and auditor.has_errors:
        print(
            f"[warn] {len(auditor.errors)} unrecoverable error(s) in {p.name}",
            file=sys.stderr,
        )
        if auditor.has_fixes:
            print(
                f"[info] {len(auditor.fixes)} fix(es) applied during recovery",
                file=sys.stderr,
            )
    return doc, auditor


def die(msg: str, code: int = 1) -> None:
    """Print to stderr and exit."""
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def match_layers(names: Iterable[str], patterns: list[str]) -> set[str]:
    """Match layer names against a list of glob patterns ('C-STORM-*')."""
    out: set[str] = set()
    for n in names:
        for pat in patterns:
            if fnmatch.fnmatchcase(n.upper(), pat.upper()):
                out.add(n)
                break
    return out


def parse_layer_patterns(s: str | None) -> list[str]:
    """Parse '--layers' argument: comma-separated globs."""
    if not s:
        return []
    return [p.strip() for p in s.split(",") if p.strip()]


def parse_bbox(s: str) -> tuple[float, float, float, float]:
    """Parse 'xmin,ymin,xmax,ymax' string."""
    parts = [float(x) for x in s.split(",")]
    if len(parts) != 4:
        die(f"--bbox must be 'xmin,ymin,xmax,ymax', got: {s}")
    return parts[0], parts[1], parts[2], parts[3]


def parse_point(s: str) -> tuple[float, float]:
    """Parse 'x,y' string."""
    parts = [float(x) for x in s.split(",")]
    if len(parts) != 2:
        die(f"point must be 'x,y', got: {s}")
    return parts[0], parts[1]


def entity_position(e) -> tuple[float, float] | None:
    """Best-effort position for an entity, for spatial filtering and reporting.

    Uses insertion point, start point, center, or first vertex depending on type.
    Returns None when no reasonable position is available.
    """
    dxf = e.dxf
    for attr in ("insert", "center", "start", "location"):
        if dxf.hasattr(attr):
            v = getattr(dxf, attr)
            return float(v[0]), float(v[1])
    # polylines
    if hasattr(e, "vertices"):
        try:
            v = next(iter(e.vertices()), None)
            if v is not None:
                return float(v[0]), float(v[1])
        except Exception:
            pass
    # try first vertex via get_points (LWPOLYLINE)
    if hasattr(e, "get_points"):
        try:
            pts = list(e.get_points("xy"))
            if pts:
                return float(pts[0][0]), float(pts[0][1])
        except Exception:
            pass
    return None


def entity_bbox(e) -> tuple[float, float, float, float] | None:
    """Try to compute an entity's bbox. Returns (xmin, ymin, xmax, ymax) or None."""
    try:
        from ezdxf import bbox  # local import — module is heavy

        b = bbox.extents([e])
        if not b.has_data:
            return None
        return (
            float(b.extmin.x),
            float(b.extmin.y),
            float(b.extmax.x),
            float(b.extmax.y),
        )
    except Exception:
        return None


def units_label(doc: Drawing) -> str:
    code = doc.header.get("$INSUNITS", 0)
    return INSUNITS.get(int(code), f"unknown({code})")


def dump_json(obj: Any) -> None:
    """Print JSON to stdout with stable, readable formatting."""
    json.dump(obj, sys.stdout, indent=2, default=_json_default, ensure_ascii=False)
    sys.stdout.write("\n")


def _json_default(o: Any) -> Any:
    # Handle ezdxf Vec3-like objects and other numerics
    if hasattr(o, "x") and hasattr(o, "y"):
        if hasattr(o, "z"):
            return [float(o.x), float(o.y), float(o.z)]
        return [float(o.x), float(o.y)]
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
