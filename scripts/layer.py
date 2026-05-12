#!/usr/bin/env python3
"""layer.py — list entities on a specific layer with key attributes.

Usage:
    python scripts/layer.py drawings/site.dxf --layer C-STORM-PIPE
    python scripts/layer.py drawings/site.dxf --layer C-STORM-PIPE --type LWPOLYLINE
    python scripts/layer.py drawings/site.dxf --layer "C-STORM-*" --limit 50
"""
from __future__ import annotations

import argparse
from pathlib import Path

from _lib import dump_json, entity_bbox, entity_position, load, match_layers


def entity_summary(e) -> dict:
    """Pull a compact set of attributes from any entity."""
    t = e.dxftype()
    d = {
        "type": t,
        "handle": str(e.dxf.handle),
        "layer": str(e.dxf.layer),
    }
    if e.dxf.hasattr("color"):
        d["color"] = int(e.dxf.color)
    if e.dxf.hasattr("linetype"):
        d["linetype"] = str(e.dxf.linetype)

    # Type-specific fields
    pos = entity_position(e)
    if pos is not None:
        d["position"] = list(pos)

    if t == "LINE":
        d["start"] = list(e.dxf.start)[:2]
        d["end"] = list(e.dxf.end)[:2]
        try:
            import math

            sx, sy = float(e.dxf.start[0]), float(e.dxf.start[1])
            ex, ey = float(e.dxf.end[0]), float(e.dxf.end[1])
            d["length"] = math.hypot(ex - sx, ey - sy)
        except Exception:
            pass
    elif t == "CIRCLE":
        d["center"] = list(e.dxf.center)[:2]
        d["radius"] = float(e.dxf.radius)
    elif t == "ARC":
        d["center"] = list(e.dxf.center)[:2]
        d["radius"] = float(e.dxf.radius)
        d["start_angle"] = float(e.dxf.start_angle)
        d["end_angle"] = float(e.dxf.end_angle)
    elif t == "LWPOLYLINE":
        try:
            pts = [list(p)[:2] for p in e.get_points("xy")]
            d["vertex_count"] = len(pts)
            d["closed"] = bool(e.closed)
            # only include first/last for brevity
            if pts:
                d["first_vertex"] = pts[0]
                d["last_vertex"] = pts[-1]
            try:
                d["length"] = float(e.length())
            except Exception:
                pass
        except Exception:
            pass
    elif t == "POLYLINE":
        try:
            pts = [list(v.dxf.location)[:2] for v in e.vertices]
            d["vertex_count"] = len(pts)
            if pts:
                d["first_vertex"] = pts[0]
                d["last_vertex"] = pts[-1]
        except Exception:
            pass
    elif t in ("TEXT", "MTEXT"):
        try:
            txt = e.dxf.text if t == "TEXT" else e.text
            d["text"] = str(txt)[:500]
        except Exception:
            pass
        try:
            d["height"] = float(e.dxf.char_height if t == "MTEXT" else e.dxf.height)
        except Exception:
            pass
    elif t == "INSERT":
        d["block_name"] = str(e.dxf.name)
        d["scale"] = [
            float(e.dxf.xscale),
            float(e.dxf.yscale),
            float(e.dxf.zscale),
        ]
        d["rotation"] = float(e.dxf.rotation)
        # block attributes
        attribs = {}
        try:
            for a in e.attribs:
                attribs[a.dxf.tag] = str(a.dxf.text)
        except Exception:
            pass
        if attribs:
            d["attributes"] = attribs
    elif t == "HATCH":
        try:
            d["pattern_name"] = str(e.dxf.pattern_name)
            d["solid_fill"] = bool(e.dxf.solid_fill)
        except Exception:
            pass
    elif t.startswith("DIMENSION"):
        try:
            d["measurement"] = float(e.get_measurement())
        except Exception:
            pass
        try:
            d["text_override"] = str(e.dxf.text)
        except Exception:
            pass

    bb = entity_bbox(e)
    if bb:
        d["bbox"] = {"min": [bb[0], bb[1]], "max": [bb[2], bb[3]]}
    return d


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file", type=Path)
    ap.add_argument(
        "--layer",
        required=True,
        help="layer name or glob pattern (e.g. 'C-STORM-*')",
    )
    ap.add_argument(
        "--type",
        default=None,
        help="filter by entity type (LINE, LWPOLYLINE, INSERT, etc.)",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=200,
        help="max entities to return (default 200)",
    )
    ap.add_argument(
        "--space",
        default="model",
        choices=["model", "paper", "all"],
        help="which space to search",
    )
    args = ap.parse_args()

    doc, _ = load(args.file)
    all_layer_names = [l.dxf.name for l in doc.layers]
    target_layers = match_layers(all_layer_names, [args.layer])
    if not target_layers:
        # also try entities that reference undefined layers
        target_layers = {args.layer}

    spaces = []
    if args.space in ("model", "all"):
        spaces.append(("modelspace", doc.modelspace()))
    if args.space in ("paper", "all"):
        for lname in doc.layout_names():
            if lname.lower() != "model":
                spaces.append((lname, doc.layouts.get(lname)))

    results = []
    truncated = False
    for space_name, space in spaces:
        for e in space:
            if e.dxf.layer not in target_layers:
                continue
            if args.type and e.dxftype() != args.type.upper():
                continue
            if len(results) >= args.limit:
                truncated = True
                break
            row = entity_summary(e)
            row["space"] = space_name
            results.append(row)
        if truncated:
            break

    out = {
        "file": str(args.file),
        "matched_layers": sorted(target_layers),
        "type_filter": args.type,
        "count": len(results),
        "truncated": truncated,
        "entities": results,
    }
    dump_json(out)


if __name__ == "__main__":
    main()
