#!/usr/bin/env python3
"""spatial.py — find entities near a point (radius) or inside a bounding box.

Usage:
    python scripts/spatial.py drawings/site.dxf --near 1234.5,6789.0 --radius 50
    python scripts/spatial.py drawings/site.dxf --bbox 1000,2000,1500,2500
    python scripts/spatial.py drawings/site.dxf --near 1234.5,6789.0 --radius 50 --type INSERT
"""
from __future__ import annotations

import argparse
from pathlib import Path

from _lib import (
    die,
    distance,
    dump_json,
    entity_bbox,
    entity_position,
    load,
    parse_bbox,
    parse_point,
)


def bboxes_overlap(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file", type=Path)
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--near", help="point 'x,y' (use with --radius)")
    grp.add_argument("--bbox", help="bbox 'xmin,ymin,xmax,ymax'")
    ap.add_argument(
        "--radius", type=float, default=10.0, help="radius for --near (default 10)"
    )
    ap.add_argument("--type", default=None, help="filter by entity type")
    ap.add_argument("--layer", default=None, help="filter by layer name (exact)")
    ap.add_argument("--limit", type=int, default=300)
    args = ap.parse_args()

    doc, _ = load(args.file)
    msp = doc.modelspace()

    if args.near:
        center = parse_point(args.near)
        radius = args.radius
        bbox_filter = (
            center[0] - radius,
            center[1] - radius,
            center[0] + radius,
            center[1] + radius,
        )
        mode = "near"
    else:
        bbox_filter = parse_bbox(args.bbox)
        center = None
        mode = "bbox"

    results = []
    truncated = False

    for e in msp:
        if args.type and e.dxftype() != args.type.upper():
            continue
        if args.layer and e.dxf.layer != args.layer:
            continue

        # Cheap test: position
        pos = entity_position(e)
        bb = entity_bbox(e)

        included = False
        dist = None
        if mode == "near":
            if pos and distance(pos, center) <= radius:
                included = True
                dist = distance(pos, center)
            elif bb and bboxes_overlap(bb, bbox_filter):
                # entity straddles the radius circle; include it
                included = True
                # estimate distance as distance from center to bb
                cx, cy = center
                clamped_x = max(bb[0], min(cx, bb[2]))
                clamped_y = max(bb[1], min(cy, bb[3]))
                dist = ((clamped_x - cx) ** 2 + (clamped_y - cy) ** 2) ** 0.5
        else:
            if bb and bboxes_overlap(bb, bbox_filter):
                included = True
            elif pos and (
                bbox_filter[0] <= pos[0] <= bbox_filter[2]
                and bbox_filter[1] <= pos[1] <= bbox_filter[3]
            ):
                included = True

        if not included:
            continue
        if len(results) >= args.limit:
            truncated = True
            break

        row = {
            "type": e.dxftype(),
            "handle": str(e.dxf.handle),
            "layer": str(e.dxf.layer),
            "position": list(pos) if pos else None,
        }
        if dist is not None:
            row["distance"] = round(dist, 4)
        if bb:
            row["bbox"] = {"min": [bb[0], bb[1]], "max": [bb[2], bb[3]]}
        if e.dxftype() == "INSERT":
            row["block_name"] = str(e.dxf.name)
        if e.dxftype() in ("TEXT", "MTEXT"):
            try:
                row["text"] = (
                    e.dxf.text if e.dxftype() == "TEXT" else e.text
                )[:200]
            except Exception:
                pass
        results.append(row)

    if mode == "near":
        results.sort(key=lambda r: r.get("distance", 1e18))

    dump_json(
        {
            "file": str(args.file),
            "mode": mode,
            "near": list(center) if center else None,
            "radius": args.radius if mode == "near" else None,
            "bbox": list(bbox_filter) if mode == "bbox" else None,
            "count": len(results),
            "truncated": truncated,
            "entities": results,
        }
    )


if __name__ == "__main__":
    main()
