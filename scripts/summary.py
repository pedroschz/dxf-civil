#!/usr/bin/env python3
"""summary.py — produce a JSON map of a DXF drawing.

Always run this first. Output is JSON to stdout.

Usage:
    python scripts/summary.py drawings/site.dxf
    python scripts/summary.py drawings/site.dxf --text-sample 50 > summary.json
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from _lib import dump_json, entity_bbox, load, units_label


def build_summary(path: Path, text_sample: int = 20) -> dict:
    doc, auditor = load(path, verbose=False)
    msp = doc.modelspace()

    # Layers ----------------------------------------------------------------
    layer_info: dict[str, dict] = {}
    for layer in doc.layers:
        layer_info[layer.dxf.name] = {
            "name": layer.dxf.name,
            "color": int(layer.dxf.color),
            "linetype": str(layer.dxf.linetype),
            "lineweight": int(getattr(layer.dxf, "lineweight", -1)),
            "frozen": bool(layer.is_frozen()),
            "locked": bool(layer.is_locked()),
            "off": bool(layer.is_off()),
            "plot": bool(getattr(layer.dxf, "plot", 1)),
            "entity_counts": {},
            "entity_total": 0,
            "bbox": None,
        }

    # Walk modelspace entities ---------------------------------------------
    entities_by_layer: dict[str, list] = defaultdict(list)
    text_samples: list[dict] = []
    type_counter: Counter = Counter()

    for e in msp:
        t = e.dxftype()
        type_counter[t] += 1
        layer_name = e.dxf.layer
        if layer_name not in layer_info:
            # entity references an undefined layer — record it
            layer_info[layer_name] = {
                "name": layer_name,
                "color": 7,
                "linetype": "Continuous",
                "lineweight": -1,
                "frozen": False,
                "locked": False,
                "off": False,
                "plot": True,
                "entity_counts": {},
                "entity_total": 0,
                "bbox": None,
                "undefined": True,
            }
        info = layer_info[layer_name]
        info["entity_counts"][t] = info["entity_counts"].get(t, 0) + 1
        info["entity_total"] += 1
        entities_by_layer[layer_name].append(e)

        # collect text samples
        if t in ("TEXT", "MTEXT") and len(text_samples) < text_sample:
            try:
                txt = e.dxf.text if t == "TEXT" else e.text
                pos = e.dxf.insert if e.dxf.hasattr("insert") else None
                text_samples.append(
                    {
                        "type": t,
                        "text": str(txt)[:200],
                        "layer": layer_name,
                        "position": [float(pos[0]), float(pos[1])] if pos else None,
                    }
                )
            except Exception:
                pass

    # Per-layer bbox via the bbox module -----------------------------------
    # We compute this best-effort; it can be slow on huge layers but is cheap
    # on typical civil drawings.
    try:
        from ezdxf import bbox

        for name, ents in entities_by_layer.items():
            try:
                b = bbox.extents(ents)
                if b.has_data:
                    layer_info[name]["bbox"] = {
                        "min": [float(b.extmin.x), float(b.extmin.y)],
                        "max": [float(b.extmax.x), float(b.extmax.y)],
                    }
            except Exception:
                pass
    except Exception:
        pass

    # Drawing extents ------------------------------------------------------
    extents = None
    try:
        from ezdxf import bbox

        b = bbox.extents(msp)
        if b.has_data:
            extents = {
                "min": [float(b.extmin.x), float(b.extmin.y)],
                "max": [float(b.extmax.x), float(b.extmax.y)],
                "width": float(b.extmax.x - b.extmin.x),
                "height": float(b.extmax.y - b.extmin.y),
            }
    except Exception:
        pass

    # Blocks ---------------------------------------------------------------
    block_inserts: Counter = Counter()
    for e in msp.query("INSERT"):
        block_inserts[e.dxf.name] += 1
    blocks = []
    for blk in doc.blocks:
        name = blk.name
        if name.startswith("*"):  # anonymous / system blocks
            continue
        blocks.append(
            {
                "name": name,
                "insertion_count": int(block_inserts.get(name, 0)),
                "entity_count": sum(1 for _ in blk),
            }
        )
    blocks.sort(key=lambda b: -b["insertion_count"])

    # XRefs ----------------------------------------------------------------
    # BLOCK entity flags: 4 = xref, 8 = xref overlay
    xrefs = []
    for blk in doc.blocks:
        try:
            block_entity = blk.block
            flags = int(getattr(block_entity.dxf, "flags", 0))
            if flags & 0xC:  # 4 | 8
                xrefs.append(
                    {
                        "name": blk.name,
                        "path": str(getattr(block_entity.dxf, "xref_path", "")),
                        "overlay": bool(flags & 8),
                    }
                )
        except Exception:
            pass

    # Layouts --------------------------------------------------------------
    layouts = [name for name in doc.layout_names()]

    # Header info ----------------------------------------------------------
    hdr = doc.header
    header_info = {
        "dxf_version": doc.dxfversion,
        "release": doc.acad_release,
        "units": units_label(doc),
        "insunits_code": int(hdr.get("$INSUNITS", 0)),
        "ltscale": float(hdr.get("$LTSCALE", 1.0)),
        "lwdisplay": bool(hdr.get("$LWDISPLAY", 0)),
        "limmin": list(hdr.get("$LIMMIN", (0, 0))),
        "limmax": list(hdr.get("$LIMMAX", (0, 0))),
    }

    # Sort layers by entity count (most populated first) -------------------
    sorted_layers = sorted(
        layer_info.values(), key=lambda x: -x["entity_total"]
    )

    return {
        "file": str(path),
        "header": header_info,
        "extents": extents,
        "entity_total": int(sum(type_counter.values())),
        "entity_types": dict(type_counter.most_common()),
        "layouts": layouts,
        "xrefs": xrefs,
        "layer_count": len(layer_info),
        "layers": sorted_layers,
        "block_count": len(blocks),
        "blocks": blocks[:50],  # cap; full list available via inspection
        "block_count_total": len(blocks),
        "text_sample": text_samples,
        "audit": {
            "errors": len(auditor.errors),
            "fixes_applied": len(auditor.fixes),
            "has_errors": bool(auditor.has_errors),
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file", type=Path, help="path to .dxf file")
    ap.add_argument(
        "--text-sample",
        type=int,
        default=20,
        help="number of TEXT/MTEXT samples to include (default 20)",
    )
    args = ap.parse_args()

    summary = build_summary(args.file, text_sample=args.text_sample)
    dump_json(summary)


if __name__ == "__main__":
    main()
