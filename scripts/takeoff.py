#!/usr/bin/env python3
"""takeoff.py — quantity takeoff: lengths, areas, and counts grouped by layer.

NOT a substitute for a licensed engineer's review. This is a first-pass
estimate. Always validate against the source drawing.

Usage:
    python scripts/takeoff.py drawings/site.dxf
    python scripts/takeoff.py drawings/site.dxf --layers "C-ROAD-*,C-CURB-*"
    python scripts/takeoff.py drawings/site.dxf --units feet
"""
from __future__ import annotations

import argparse
import math
from collections import defaultdict
from pathlib import Path

from _lib import (
    dump_json,
    load,
    match_layers,
    parse_layer_patterns,
    units_label,
)


def polyline_length(e) -> float:
    """Compute LWPOLYLINE / POLYLINE length, ignoring bulges (good enough for QTO)."""
    try:
        if hasattr(e, "length"):
            return float(e.length())
    except Exception:
        pass
    # fallback: sum segments
    pts = []
    try:
        if e.dxftype() == "LWPOLYLINE":
            pts = [(float(p[0]), float(p[1])) for p in e.get_points("xy")]
            if e.closed and pts:
                pts.append(pts[0])
        elif e.dxftype() == "POLYLINE":
            pts = [
                (float(v.dxf.location[0]), float(v.dxf.location[1]))
                for v in e.vertices
            ]
            if getattr(e, "is_closed", False) and pts:
                pts.append(pts[0])
    except Exception:
        return 0.0
    return sum(
        math.hypot(b[0] - a[0], b[1] - a[1])
        for a, b in zip(pts, pts[1:])
    )


def polygon_area(pts: list[tuple[float, float]]) -> float:
    """Shoelace formula for a closed polygon."""
    if len(pts) < 3:
        return 0.0
    a = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + [pts[0]]):
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def polyline_area_if_closed(e) -> float:
    if e.dxftype() == "LWPOLYLINE":
        if not e.closed:
            return 0.0
        try:
            pts = [(float(p[0]), float(p[1])) for p in e.get_points("xy")]
            return polygon_area(pts)
        except Exception:
            return 0.0
    if e.dxftype() == "POLYLINE":
        if not getattr(e, "is_closed", False):
            return 0.0
        try:
            pts = [
                (float(v.dxf.location[0]), float(v.dxf.location[1]))
                for v in e.vertices
            ]
            return polygon_area(pts)
        except Exception:
            return 0.0
    return 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file", type=Path)
    ap.add_argument(
        "--layers",
        default=None,
        help="comma-separated globs to include (default: all)",
    )
    ap.add_argument(
        "--units",
        default=None,
        help="override units label for output (drawing units are used regardless)",
    )
    args = ap.parse_args()

    doc, _ = load(args.file)
    msp = doc.modelspace()

    include = parse_layer_patterns(args.layers)
    all_layer_names = [l.dxf.name for l in doc.layers]
    if include:
        keep = match_layers(all_layer_names, include)
    else:
        keep = None  # all

    per_layer: dict[str, dict] = defaultdict(
        lambda: {
            "line_length": 0.0,
            "polyline_length": 0.0,
            "closed_polyline_area": 0.0,
            "hatch_area": 0.0,
            "circle_count": 0,
            "circle_total_area": 0.0,
            "block_inserts": defaultdict(int),
            "entity_counts": defaultdict(int),
        }
    )

    for e in msp:
        layer = e.dxf.layer
        if keep is not None and layer not in keep:
            continue
        t = e.dxftype()
        bucket = per_layer[layer]
        bucket["entity_counts"][t] += 1

        if t == "LINE":
            try:
                sx, sy = float(e.dxf.start[0]), float(e.dxf.start[1])
                ex, ey = float(e.dxf.end[0]), float(e.dxf.end[1])
                bucket["line_length"] += math.hypot(ex - sx, ey - sy)
            except Exception:
                pass
        elif t in ("LWPOLYLINE", "POLYLINE"):
            bucket["polyline_length"] += polyline_length(e)
            bucket["closed_polyline_area"] += polyline_area_if_closed(e)
        elif t == "CIRCLE":
            bucket["circle_count"] += 1
            try:
                r = float(e.dxf.radius)
                bucket["circle_total_area"] += math.pi * r * r
            except Exception:
                pass
        elif t == "ARC":
            try:
                r = float(e.dxf.radius)
                a0 = math.radians(float(e.dxf.start_angle))
                a1 = math.radians(float(e.dxf.end_angle))
                # arc length, accounting for ccw direction
                sweep = (a1 - a0) % (2 * math.pi)
                bucket["polyline_length"] += r * sweep
            except Exception:
                pass
        elif t == "HATCH":
            try:
                bucket["hatch_area"] += float(e.dxf.elevation) * 0  # placeholder
                # ezdxf doesn't expose hatch area directly; compute from boundary
                # paths is non-trivial. We sum bbox area as a coarse proxy.
                from ezdxf import bbox

                b = bbox.extents([e])
                if b.has_data:
                    bucket["hatch_area"] += float(
                        (b.extmax.x - b.extmin.x) * (b.extmax.y - b.extmin.y)
                    )
            except Exception:
                pass
        elif t == "INSERT":
            bucket["block_inserts"][str(e.dxf.name)] += 1

    # Convert defaultdicts to plain dicts and round
    result_layers = []
    for name, b in sorted(per_layer.items()):
        result_layers.append(
            {
                "layer": name,
                "line_length": round(b["line_length"], 4),
                "polyline_length": round(b["polyline_length"], 4),
                "total_length": round(
                    b["line_length"] + b["polyline_length"], 4
                ),
                "closed_polyline_area": round(b["closed_polyline_area"], 4),
                "hatch_area_bbox_proxy": round(b["hatch_area"], 4),
                "circle_count": b["circle_count"],
                "circle_total_area": round(b["circle_total_area"], 4),
                "block_inserts": dict(b["block_inserts"]),
                "entity_counts": dict(b["entity_counts"]),
            }
        )

    dump_json(
        {
            "file": str(args.file),
            "units": args.units or units_label(doc),
            "layer_count": len(result_layers),
            "notes": [
                "Areas labeled 'bbox_proxy' are bbox approximations, not true geometry.",
                "Arc lengths are included in polyline_length.",
                "ALWAYS verify before billable use.",
            ],
            "layers": result_layers,
        }
    )


if __name__ == "__main__":
    main()
