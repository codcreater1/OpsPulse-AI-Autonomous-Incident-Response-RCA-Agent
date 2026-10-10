"""Render the demo output as an animated terminal SVG for the README (no external tools needed).

    python -m scripts.render_demo_svg                 # runs `python -m scripts.demo` (MOCK model) and writes the SVG
    python -m scripts.render_demo_svg --input out.txt # render captured output instead

The animation is plain CSS: every line fades in after the previous one and, where CSS animation is not
supported, all lines are simply visible. The first line states that the model is scripted - the recording
demonstrates the pipeline, not the model.
"""

from __future__ import annotations

import argparse
import html
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images" / "demo.svg"
MAX_COLUMNS = 112
LINE_HEIGHT = 19
ANSI = re.compile(r"\x1b\[[0-9;]*m")
COMMAND = "$ python -m scripts.demo        # MOCK model: scripted reply, offline, ~3 s"


def _capture() -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.demo"], cwd=ROOT, capture_output=True, text=True, timeout=300, check=False
    )
    return proc.stdout


def _lines(raw: str) -> list[str]:
    cleaned = []
    for line in ANSI.sub("", raw).splitlines():
        if line.startswith("report:") or "HTTP Request" in line:  # local paths and client noise
            continue
        cleaned.append(line if len(line) <= MAX_COLUMNS else line[: MAX_COLUMNS - 1] + "…")
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    return [COMMAND, "", *cleaned]


def _class(line: str) -> str:
    if line.startswith("$"):
        return "cmd"
    if line.startswith("==="):
        return "head"
    if line.startswith("RESULT") or ("passed" in line and "failed" not in line):
        return "ok"
    if "failed" in line or line.startswith("TypeError") or (line.startswith("-") and not line.startswith("---")):
        return "bad"
    if line.startswith("+") and not line.startswith("+++"):
        return "add"
    return "plain"


def render(lines: list[str]) -> str:
    width, height = 940, 54 + LINE_HEIGHT * len(lines)
    delay, rows = 0.0, []
    for index, line in enumerate(lines):
        if line.startswith("==="):
            delay += 0.45
        delay += 0.11
        y = 46 + LINE_HEIGHT * index
        rows.append(
            f'<text x="20" y="{y}" class="{_class(line)} l" style="animation-delay:{delay:.2f}s" '
            f'xml:space="preserve">{html.escape(line) or "&#160;"}</text>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" \
viewBox="0 0 {width} {height}" role="img" aria-label="Terminal recording of the OpsPulse demo (scripted model)">
<style>
  .bg {{ fill: #0d1117; }} .bar {{ fill: #161b22; }}
  text {{ font: 13px/1 ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; fill: #c9d1d9; }}
  .cmd {{ fill: #79c0ff; }} .head {{ fill: #d2a8ff; font-weight: bold; }} .ok {{ fill: #56d364; }}
  .bad {{ fill: #ff7b72; }} .add {{ fill: #56d364; }} .plain {{ fill: #c9d1d9; }}
  .l {{ animation: show .25s ease-out backwards; }}
  @keyframes show {{ from {{ opacity: 0; transform: translateY(3px); }} to {{ opacity: 1; transform: none; }} }}
  @media (prefers-reduced-motion: reduce) {{ .l {{ animation: none; }} }}
</style>
<rect class="bg" width="{width}" height="{height}" rx="8"/>
<rect class="bar" width="{width}" height="30" rx="8"/>
<circle cx="18" cy="15" r="5" fill="#ff5f56"/><circle cx="36" cy="15" r="5" fill="#ffbd2e"/>
<circle cx="54" cy="15" r="5" fill="#27c93f"/>
<text x="{width // 2}" y="19" text-anchor="middle" style="fill:#8b949e">opspulse-ai - demo (mock model)</text>
{chr(10).join(rows)}
</svg>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=pathlib.Path, help="captured demo output (default: run the demo)")
    parser.add_argument("--out", type=pathlib.Path, default=OUT)
    args = parser.parse_args(argv)
    raw = args.input.read_text(encoding="utf-8") if args.input else _capture()
    lines = _lines(raw)
    if len(lines) < 10:
        print("demo produced too little output; nothing written", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(lines), encoding="utf-8")
    print(f"wrote {args.out} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
