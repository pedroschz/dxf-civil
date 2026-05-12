#!/usr/bin/env python3
"""render.py — render a DXF to PNG for visual inspection.

Use after summary.py to see the drawing before reasoning about geometry.

Usage:
    python scripts/render.py drawings/site.dxf --out preview.png
    python scripts/render.py drawings/site.dxf --layers "C-STORM-*,C-SAN-*" --dpi 300 --out storm.png
    python scripts/render.py drawings/site.dxf --layout "Sheet C-101" --out c101.png
    python scripts/render.py drawings/site.dxf --bbox 1000,2000,1500,2500 --out detail.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

from _lib import die, load, match_layers, parse_bbox, parse_layer_patterns


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file", type=Path, help="path to .dxf file")
    ap.add_argument("--out", type=Path, required=True, help="output image path")
    ap.add_argument(
        "--layout",
        default=None,
        help="paperspace layout name (default: modelspace)",
    )
    ap.add_argument(
        "--layers",
        default=None,
        help="comma-separated layer globs to include (e.g. 'C-STORM-*,C-SAN-*')",
    )
    ap.add_argument(
        "--exclude-layers",
        default=None,
        help="comma-separated layer globs to exclude",
    )
    ap.add_argument(
        "--bbox",
        default=None,
        help="crop to bbox 'xmin,ymin,xmax,ymax'",
    )
    ap.add_argument("--dpi", type=int, default=150, help="output DPI (default 150)")
    ap.add_argument(
        "--bg",
        default="white",
        choices=["white", "black", "transparent"],
        help="background color",
    )
    ap.add_argument(
        "--size",
        default="12,9",
        help="figure size in inches 'W,H' (default 12,9)",
    )
    args = ap.parse_args()

    # Import matplotlib lazily so the script fails with a clear message if
    # the user hasn't installed the optional drawing add-on dependencies.
    try:
        import matplotlib.pyplot as plt
        from ezdxf.addons.drawing import Frontend, RenderContext
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
        from ezdxf.addons.drawing.config import Configuration
    except ImportError as e:
        die(
            f"missing dependency: {e}. Install with: "
            "pip install 'ezdxf[draw]' matplotlib"
        )

    doc, _ = load(args.file, verbose=True)

    # Pick layout
    if args.layout:
        try:
            layout = doc.layouts.get(args.layout)
        except Exception:
            available = ", ".join(doc.layout_names())
            die(f"layout '{args.layout}' not found. available: {available}")
    else:
        layout = doc.modelspace()

    # Apply layer filters by toggling layer visibility on a working copy of
    # the doc. We don't write the doc back so this is safe.
    include = parse_layer_patterns(args.layers)
    exclude = parse_layer_patterns(args.exclude_layers)
    all_layer_names = [l.dxf.name for l in doc.layers]
    if include:
        keep = match_layers(all_layer_names, include)
        for layer in doc.layers:
            if layer.dxf.name not in keep:
                layer.off()
    if exclude:
        drop = match_layers(all_layer_names, exclude)
        for layer in doc.layers:
            if layer.dxf.name in drop:
                layer.off()

    # Build the figure
    w, h = (float(x) for x in args.size.split(","))
    fig = plt.figure(figsize=(w, h), dpi=args.dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    if args.bg == "black":
        fig.patch.set_facecolor("black")
        ax.set_facecolor("black")
    elif args.bg == "transparent":
        fig.patch.set_alpha(0)
        ax.set_facecolor("none")

    ctx = RenderContext(doc)
    backend = MatplotlibBackend(ax)
    cfg = Configuration()
    Frontend(ctx, backend, config=cfg).draw_layout(layout, finalize=True)

    # Apply bbox crop if requested
    if args.bbox:
        xmin, ymin, xmax, ymax = parse_bbox(args.bbox)
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)

    ax.set_aspect("equal")
    ax.axis("off")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        args.out,
        dpi=args.dpi,
        bbox_inches="tight",
        pad_inches=0.1,
        transparent=(args.bg == "transparent"),
    )
    plt.close(fig)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
