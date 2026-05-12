# examples/

Drop reference drawings, annotated screenshots, or sample JSON outputs here
to help the agent ground its understanding of your office's drafting style.

A good first example to add:

1. A typical site plan from your office (DXF, anonymized if needed).
2. A rendered PNG of it (run `python ../scripts/render.py <file>.dxf --out ref.png`).
3. The summary JSON (run `python ../scripts/summary.py <file>.dxf > ref-summary.json`).
4. A short `NOTES.md` describing what's idiomatic about it — layers used,
   block conventions, scale, anything an outsider would miss.

Claude Code will read these when reasoning about new drawings and produce
output that matches your office's house style rather than a generic default.
