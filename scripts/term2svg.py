"""Render a captured terminal transcript (.txt) as a terminal-window SVG.

usage: python scripts/term2svg.py <capture.txt> <out.svg> "<window title>"
The text is reproduced verbatim; only colours are added (prompt lines,
errors, PASS/FAIL keywords) for readability.
"""

import re
import sys
from xml.sax.saxutils import escape

CHAR_W, LINE_H, PAD, BAR = 7.8, 18, 16, 30
NBSP = "\u00a0"  # keeps column alignment in every SVG renderer


def colour(line: str) -> str:
    if line.startswith(("$ ", "promql> ", "logcli> ")):
        return "#7ee787"
    if re.search(r"Error|denied|FAIL|Forbidden|failed", line):
        return "#ff7b72"
    if re.search(r"PASS|passed|reached|created|Synced|Running|Healthy", line):
        return "#79c0ff"
    return "#e6edf3"


def main(src: str, dst: str, title: str) -> None:
    lines = open(src, encoding="utf-8").read().rstrip("\n").split("\n")
    width = int(max(max(len(x) for x in lines) * CHAR_W + 2 * PAD, 640))
    height = int(BAR + PAD + len(lines) * LINE_H + PAD)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" rx="8" fill="#0d1117"/>',
        f'<rect width="{width}" height="{BAR}" rx="8" fill="#21262d"/>',
        f'<rect y="{BAR - 8}" width="{width}" height="8" fill="#21262d"/>',
        '<circle cx="18" cy="15" r="6" fill="#ff5f56"/>',
        '<circle cx="38" cy="15" r="6" fill="#ffbd2e"/>',
        '<circle cx="58" cy="15" r="6" fill="#27c93f"/>',
        f'<text x="{width / 2}" y="20" fill="#8b949e" font-family="Menlo,monospace" '
        f'font-size="12" text-anchor="middle">{escape(title)}</text>',
        '<g font-family="Menlo,Consolas,monospace" font-size="13" xml:space="preserve" style="white-space:pre">',
    ]
    for i, line in enumerate(lines):
        y = BAR + PAD + (i + 1) * LINE_H - 4
        out.append(f'<text x="{PAD}" y="{y}" fill="{colour(line)}">{escape(line).replace(" ", NBSP)}</text>')
    out += ["</g>", "</svg>"]
    open(dst, "w", encoding="utf-8").write("\n".join(out))


if __name__ == "__main__":
    main(*sys.argv[1:4])
