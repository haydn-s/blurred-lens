"""Build the poster as HTML, then let Chrome turn it into a print-ready PDF.

    python -m deliverables.make_poster_html            # HTML + PDF
    python -m deliverables.make_poster_html --check    # verify the numbers only

Why HTML. The first version of this poster placed every element at a hand-computed y coordinate
and guessed how long each line would wrap -- which is where the odd gaps came from, because a
guess is wrong by a little everywhere and the errors stack down the page. A browser does real text
layout, so a grid of columns simply fits, and what you see is what prints.

Chrome renders it to a vector PDF at exactly 24 by 36 inches, which is what a print shop wants.
`make_poster.py` then wraps that render into the .pptx the brief asks for.
"""

import argparse
import html
import subprocess
import sys
from pathlib import Path

from blurred_lens.config import ROOT
from deliverables import poster_content as C
from deliverables.make_poster import check_numbers

HERE = Path(__file__).resolve().parent
OUT_HTML = HERE / "poster.html"
OUT_PDF = HERE / "Poster Presentation.pdf"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

e = html.escape


def points(items, plain=False):
    out = []
    for item in items:
        head, body = item if isinstance(item, tuple) else (None, item)
        cls = "point plain" if plain else "point"
        parts = [f'<div class="{cls}"><div class="dot">●</div>']
        if head:
            parts.append(f"<h3>{e(head)}</h3>")
        parts.append(f"<p>{e(body)}</p></div>")
        out.append("".join(parts))
    return "\n".join(out)


def strip(css_class, caption, figure, labels):
    cells = "".join(f"<div>{e(n)}<em>{e(v)}</em></div>" for n, v in labels)
    return (f'<div class="strip {css_class}">'
            f'<div class="caption">{e(caption)}</div>'
            f'<div class="labels">{cells}</div>'
            f'<img src="figures/{figure}" alt="">'
            f"</div>")


def render() -> str:
    stats = "".join(f"<div class='stat'><b>{e(b)}</b><span>{e(s)}</span></div>" for b, s in C.STATS)
    steps = "".join(
        f"<div class='step'><div class='n'>{i + 1}</div><h3>{e(h)}</h3><p>{e(b)}</p></div>"
        for i, (h, b) in enumerate(C.PROCESS))
    problem = "".join(f"<p>{e(part)}</p>" for part in C.PROBLEM.split("\n\n"))
    widest = max(v for _, v in C.EXPLAINS)
    bars = "".join(
        f"<div class='bar'><div class='lab'>{e(l)}</div>"
        f"<div class='track' style='width:{v / widest * 100:.1f}%'></div>"
        f"<div class='val'>{v}%</div></div>" for l, v in C.EXPLAINS)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{e(C.TITLE)} — poster</title>
<link rel="stylesheet" href="poster.css">
</head><body>
<div class="page">

  <header class="masthead">
    <h1>{e(C.TITLE)}</h1>
    <p class="subtitle">{e(C.SUBTITLE)}</p>
    <p class="byline">{e(C.BYLINE)}</p>
  </header>

  <div class="stats">{stats}</div>

  <section>
    <h2>{e(C.PROBLEM_HEAD)}</h2>
    <div class="two">{problem}</div>
  </section>

  <section>
    <h2>{e(C.PROCESS_HEAD)}</h2>
    <div class="five">{steps}</div>
  </section>

  <section>
    <h2>{e(C.FINDINGS_HEAD)}</h2>
    <h3>{e(C.GRID_CAPTION)}</h3>
    <div class="strips" style="margin-top:.14in">
      {strip("warm", "the four it draws warmest", "warm-row.jpg",
             [("Niger", "+1.93"), ("Nigeria", "+1.55"), ("Chad", "+1.46"), ("Mali", "+1.41")])}
      {strip("cool", "the four it draws coolest", "cool-row.jpg",
             [("Norway", "−1.83"), ("Australia", "−1.73"),
              ("Costa Rica", "−1.39"), ("South Africa", "−1.38")])}
    </div>
    <p class="note"><b>{e(C.GRID_NOTE_HEAD)}</b> &nbsp;{e(C.GRID_NOTE)}</p>
    <div class="points">{points(C.FINDINGS)}</div>
    <hr class="thin">
    <div class="mapband" style="margin-top:.3in">
      <div>
        <h3>{e(C.MAP_CAPTION)}</h3>
        <img src="figures/world-map.png" alt="">
        <p class="note">{e(C.MAP_NOTE)}</p>
      </div>
      <div>
        <h3>{e(C.EXPLAINS_HEAD)}</h3>
        <div class="bars">{bars}</div>
        <p class="note">{e(C.EXPLAINS_NOTE)}</p>
      </div>
    </div>
  </section>

  <section>
    <h2>{e(C.MEANS_HEAD)}</h2>
    <div class="points">{points(C.MEANS)}</div>
  </section>

  <section>
    <div class="two">
      <div><h2>{e(C.NEXT_HEAD)}</h2>
        <div class="points" style="grid-template-columns:1fr">{points(C.NEXT, plain=True)}</div></div>
      <div><h2>{e(C.LIMITS_HEAD)}</h2><p class="note">{e(C.LIMITS)}</p></div>
    </div>
  </section>

  <div class="foot">{e(C.FOOTER)}</div>
</div>
</body></html>"""


def to_pdf(source: Path, target: Path) -> None:
    """Chrome headless, which honours @page and keeps the text as vectors."""
    if not CHROME.exists():
        print(f"  (skipping the PDF: no Chrome at {CHROME})")
        return
    subprocess.run([str(CHROME), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    "--user-data-dir=/tmp/cr-poster", f"--print-to-pdf={target}", str(source)],
                   check=False, capture_output=True, timeout=180)
    subprocess.run(["pkill", "-f", "user-data-dir=/tmp/cr-poster"], capture_output=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the poster as HTML and PDF.")
    ap.add_argument("--check", action="store_true", help="verify the numbers, write nothing")
    args = ap.parse_args()

    problems = check_numbers()
    print(f"  numbers: {'OK' if not problems else str(len(problems)) + ' problem(s)'}")
    for item in problems:
        print(f"    - {item}")
    if args.check:
        sys.exit(1 if problems else 0)
    if problems:
        sys.exit("\nRefusing to build: the poster's numbers no longer match the run.")

    OUT_HTML.write_text(render(), encoding="utf-8")
    print(f"  {OUT_HTML.relative_to(ROOT)}")
    to_pdf(OUT_HTML, OUT_PDF)
    if OUT_PDF.exists():
        import re
        box = re.search(rb"/MediaBox\s*\[([^\]]+)\]", OUT_PDF.read_bytes())
        size = [float(v) for v in box.group(1).split()] if box else [0, 0, 0, 0]
        print(f"  {OUT_PDF.relative_to(ROOT)}  {OUT_PDF.stat().st_size / 1e6:.1f} MB  "
              f"{(size[2] - size[0]) / 72:.2f}in x {(size[3] - size[1]) / 72:.2f}in")


if __name__ == "__main__":
    main()
