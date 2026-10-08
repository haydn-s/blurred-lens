"""Verify the poster's claims, and wrap the rendered page into the .pptx the brief asks for.

    python -m deliverables.make_poster          # check the numbers, then write the .pptx
    python -m deliverables.make_poster --check  # check the numbers only

The poster itself is laid out in HTML and CSS (`poster.html`, `poster.css`, built by
`make_poster_html.py`) and rendered by Chrome. An earlier version of this file placed every element
at a hand-computed coordinate and estimated how each line would wrap; the estimates were wrong by a
little everywhere and the errors stacked into visible gaps. A browser does real text layout, so the
columns simply fit.

What a print shop should be given is `Poster Presentation.pdf`: Chrome writes it at exactly 24 by
36 inches with the text still vector, so it prints sharp at any size. The .pptx here carries the
same page as a high-resolution image, because the deliverable was asked for in that format.
"""

import argparse
import json
import sys
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.util import Inches

from blurred_lens.config import ROOT, load_config, run_dir
from blurred_lens.report import build_report

HERE = Path(__file__).resolve().parent
RENDER = HERE / "figures" / "poster-print.png"
OUT = HERE / "Poster Presentation.pptx"
W, H = 24.0, 36.0


def check_numbers() -> list[str]:
    """Read the run back and confirm the poster still says what the data says."""
    cfg = load_config()
    r = build_report(cfg, run_dir(cfg, "phase2-noon"), "cast_b", permutations=4000,
                     baseline_dir=run_dir(cfg, "phase2-baseline-noon"))
    c = r["countries"]
    problems = []

    def want(label, actual, expected, tol=0.015):
        if abs(actual - expected) > tol:
            problems.append(f"{label}: poster says {expected}, data says {actual:.3f}")

    warmer = sum(1 for d in c.values() if d.get("baseline_index", 0) > 0)
    if warmer != 53:
        problems.append(f"'53 of 60' warmer than default: data says {warmer}")
    if len(c) != 60:
        problems.append(f"60 countries: data has {len(c)}")

    ranked = sorted(c.items(), key=lambda kv: -kv[1]["index"])
    top = [(d["name"], round(d["index"], 2)) for _, d in ranked[:4]]
    bottom = [(d["name"], round(d["index"], 2)) for _, d in ranked[-4:]][::-1]
    if top != [("Niger", 1.93), ("Nigeria", 1.55), ("Chad", 1.46), ("Mali", 1.41)]:
        problems.append(f"warm row labels: data says {top}")
    if bottom != [("Norway", -1.83), ("Australia", -1.73), ("Costa Rica", -1.39),
                  ("South Africa", -1.38)]:
        problems.append(f"cool row labels: data says {bottom}")

    want("controls r2", r["controls"]["r2"] * 100, 46, tol=1.0)
    alone = {n: v * 100 for n, v in r["controls"]["alone"].items()}
    for field, expected in (("latitude", 5), ("precipitation_mm", 18),
                            ("temperature_c", 25), ("forest_pct", 30)):
        want(f"{field} alone", alone[field], expected, tol=1.0)
    net = r["groups_net_of_controls"]
    want("low income, controlled", net["income"]["Low income"]["d"], 0.52, tol=0.015)
    want("Africa, controlled", net["region"]["Africa"]["d"], -0.02, tol=0.015)
    want("Asia, controlled", net["region"]["Asia"]["d"], 0.70, tol=0.015)
    raw = r["groups"]
    want("low income, raw", raw["income"]["Low income"]["d"], 0.72, tol=0.015)
    want("Asia, raw", raw["region"]["Asia"]["d"], 0.60, tol=0.015)

    total = sum(1 for _ in (ROOT / "outputs").glob("phase2-*/images/*/*/*.jpg"))
    if total != 61488:
        problems.append(f"61,488 images: disk has {total:,}")

    # The income-latitude correlation, with ties sharing a rank. Income has four distinct values,
    # so nearly every pair is tied and breaking ties by sort order gives a different, wrong answer
    # -- which is how the poster once came to claim 0.24 against a true 0.25.
    income = json.loads((ROOT / "data/income_groups.json").read_text())
    equator = {c["iso_a3"]: abs(c["latitude"])
               for c in json.loads((ROOT / "data/countries.json").read_text())}
    order = {"LIC": 0, "LMC": 1, "UMC": 2, "HIC": 3}

    def ranks(values):
        placed = sorted(range(len(values)), key=lambda i: values[i])
        out, k = [0.0] * len(values), 0
        while k < len(placed):
            j = k
            while j + 1 < len(placed) and values[placed[j + 1]] == values[placed[k]]:
                j += 1
            for t in range(k, j + 1):
                out[placed[t]] = (k + j) / 2
            k = j + 1
        return out

    def rho(codes):
        xs = ranks([order[income["countries"][i]] for i in codes])
        ys = ranks([equator[i] for i in codes])
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        den = (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** 0.5
        return num / den if den else 0.0

    want("rho, this run", rho(cfg["prompts"]["countries"]), 0.25, tol=0.005)
    want("rho, worldwide", rho([i for i in equator if income["countries"].get(i)]), 0.49, tol=0.005)
    return problems


def build_pptx(render: Path, out: Path) -> None:
    """One 24x36 slide carrying the rendered page, edge to edge."""
    with Image.open(render) as im:
        dpi = im.width / W
        if abs(im.height / H - dpi) > 1:
            raise SystemExit(f"{render.name} is {im.width}x{im.height}, which is not {W}x{H} in "
                             f"proportion \u2014 re-render it.")
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_picture(str(render), 0, 0, Inches(W), Inches(H))
    prs.save(out)
    print(f"  {out.relative_to(ROOT)}  {out.stat().st_size / 1e6:.1f} MB  "
          f"({W:g}in x {H:g}in at {dpi:.0f} dpi)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Check the poster's numbers and build the .pptx.")
    ap.add_argument("--check", action="store_true", help="check the numbers, write nothing")
    args = ap.parse_args()

    problems = check_numbers()
    print(f"  numbers: {'OK' if not problems else str(len(problems)) + ' problem(s)'}")
    for item in problems:
        print(f"    - {item}")
    if args.check:
        sys.exit(1 if problems else 0)
    if problems:
        sys.exit("\nRefusing to build: the poster's numbers no longer match the run.")
    if not RENDER.exists():
        sys.exit(f"\nNo render at {RENDER}. Run `python -m deliverables.make_poster_html` first, "
                 f"then screenshot poster.html with Chrome at --force-device-scale-factor=2.")
    build_pptx(RENDER, OUT)


if __name__ == "__main__":
    main()
