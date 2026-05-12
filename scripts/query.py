#!/usr/bin/env python3
"""query.py — search TEXT, MTEXT, attributes, and dimension overrides by regex.

Usage:
    python scripts/query.py drawings/site.dxf --pattern "MH-\\d+"
    python scripts/query.py drawings/site.dxf --pattern "STA \\d+\\+\\d+" --layer "*-TEXT"
    python scripts/query.py drawings/site.dxf --pattern "TITLE BLOCK"
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from _lib import dump_json, entity_position, load, match_layers


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file", type=Path)
    ap.add_argument(
        "--pattern", required=True, help="regex (case-insensitive by default)"
    )
    ap.add_argument("--case-sensitive", action="store_true")
    ap.add_argument(
        "--layer",
        default=None,
        help="restrict to layer(s) matching this glob (e.g. '*-TEXT')",
    )
    ap.add_argument(
        "--limit", type=int, default=500, help="max hits to return (default 500)"
    )
    args = ap.parse_args()

    flags = 0 if args.case_sensitive else re.IGNORECASE
    try:
        pat = re.compile(args.pattern, flags)
    except re.error as e:
        print(f"error: invalid regex: {e}", file=__import__("sys").stderr)
        raise SystemExit(2)

    doc, _ = load(args.file)
    all_layer_names = [l.dxf.name for l in doc.layers]
    layer_filter = (
        match_layers(all_layer_names, [args.layer]) if args.layer else None
    )

    hits = []
    truncated = False

    def check_layer(name: str) -> bool:
        return layer_filter is None or name in layer_filter

    # Search all layouts: modelspace + every paperspace
    for layout_name in doc.layout_names():
        layout = doc.layouts.get(layout_name)
        for e in layout:
            if not check_layer(e.dxf.layer):
                continue
            t = e.dxftype()
            texts: list[tuple[str, str]] = []  # (source_field, value)
            try:
                if t == "TEXT":
                    texts.append(("text", e.dxf.text))
                elif t == "MTEXT":
                    texts.append(("text", e.text))
                elif t == "INSERT":
                    for a in e.attribs:
                        texts.append((f"attrib:{a.dxf.tag}", a.dxf.text))
                elif t.startswith("DIMENSION"):
                    if e.dxf.hasattr("text") and e.dxf.text not in ("<>", ""):
                        texts.append(("override", e.dxf.text))
                elif t in ("ATTDEF", "ATTRIB"):
                    texts.append((f"{t.lower()}:{e.dxf.tag}", e.dxf.text))
            except Exception:
                continue

            for source, val in texts:
                if val is None:
                    continue
                s = str(val)
                m = pat.search(s)
                if not m:
                    continue
                if len(hits) >= args.limit:
                    truncated = True
                    break
                pos = entity_position(e)
                hits.append(
                    {
                        "type": t,
                        "source": source,
                        "text": s[:500],
                        "match": m.group(0),
                        "layer": str(e.dxf.layer),
                        "space": layout_name,
                        "position": list(pos) if pos else None,
                        "handle": str(e.dxf.handle),
                    }
                )
            if truncated:
                break
        if truncated:
            break

    dump_json(
        {
            "file": str(args.file),
            "pattern": args.pattern,
            "count": len(hits),
            "truncated": truncated,
            "hits": hits,
        }
    )


if __name__ == "__main__":
    main()
