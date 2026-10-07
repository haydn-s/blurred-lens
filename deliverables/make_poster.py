"""Build the conference poster: deliverables/Poster Presentation.pptx, 24in wide by 36in tall.

    python -m deliverables.make_poster              # the .pptx, plus an HTML proof beside it
    python -m deliverables.make_poster --check      # only verify the numbers against the run

One layout, two outputs. `BLOCKS` places every element in inches on the 24x36 page, and both the
PowerPoint writer and the HTML proof read it, so what the proof shows in a browser is the geometry
the .pptx gets. The proof exists because this machine has no LibreOffice to render a .pptx back to
an image, and a poster that is going to be printed should be looked at before it is.

Print decisions worth knowing:
  - White ground. The website is near-black, which prints as a heavy slab of ink, bands on most
    plotters and hides the photographs. The amber-blue scale carries the identity instead.
  - The figures are drawn at 300 dpi by deliberables.make_figures; the photographs are the model's
    own 1024px output placed about five inches wide, which is roughly 200 dpi -- right for a poster
    read at arm's length.
  - Safe fonts only (Cambria headings, Calibri body): whatever renders this file has them.
"""

import argparse
import json
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

from blurred_lens.config import ROOT, load_config, run_dir
from blurred_lens.report import build_report
from deliverables import poster_content as C

HERE = Path(__file__).resolve().parent
FIGURES = HERE / "figures"
OUT = HERE / "Poster Presentation.pptx"
PROOF = HERE / "figures" / "poster-proof.html"

W, H = 24.0, 36.0          # inches
M = 1.1                    # outer margin
COL = (W - 2 * M - 0.9) / 2  # two-column width below the figures

INK = "1A1A1A"
MUTED = "5F6670"
RULE = "D8DCE2"
WARM = "B07C1F"            # darkened from the scale's #C2923F so it holds up as text on white
COOL = "2F6CA8"
TINT = "FBF7EF"            # the faintest warm wash, for callout cards
PAPER = "FFFFFF"
HEAD, BODY = "Cambria", "Calibri"


def rgb(h): return RGBColor.from_string(h)


class Poster:
    def __init__(self):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(W), Inches(H)
        self.slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])  # blank
        self.boxes = []  # every placed rectangle, for the overlap check

    # ---- primitives ------------------------------------------------------------------------
    def _record(self, name, x, y, w, h, **extra):
        self.boxes.append({"name": name, "x": x, "y": y, "w": w, "h": h, **extra})

    def text(self, name, x, y, w, h, runs, *, size, color=INK, font=BODY, bold=False,
             align="l", leading=1.08, space_after=0, italic=False, anchor="t"):
        """`runs` is a string or a list of (text, {overrides}) pairs."""
        box = self.slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE,
                              "b": MSO_ANCHOR.BOTTOM}[anchor]
        paragraphs = runs if isinstance(runs, list) else [(runs, {})]
        for i, (chunk, over) in enumerate(paragraphs):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[
                over.get("align", align)]
            p.line_spacing = over.get("leading", leading)
            p.space_after = Pt(over.get("space_after", space_after))
            r = p.add_run()
            r.text = chunk
            f = r.font
            f.name = over.get("font", font)
            f.size = Pt(over.get("size", size))
            f.bold = over.get("bold", bold)
            f.italic = over.get("italic", italic)
            f.color.rgb = rgb(over.get("color", color))
        self._record(name, x, y, w, h, kind="text", runs=[
            (chunk, {"size": over.get("size", size), "font": over.get("font", font),
                     "bold": over.get("bold", bold), "italic": over.get("italic", italic),
                     "color": over.get("color", color), "align": over.get("align", align),
                     "leading": over.get("leading", leading)})
            for chunk, over in paragraphs], anchor=anchor)
        return box

    def card(self, name, x, y, w, h, fill=TINT):
        from pptx.enum.shapes import MSO_SHAPE
        shape = self.slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                            Inches(x), Inches(y), Inches(w), Inches(h))
        shape.adjustments[0] = 0.04
        shape.fill.solid()
        shape.fill.fore_color.rgb = rgb(fill)
        shape.line.fill.background()
        shape.shadow.inherit = False
        self._record(name, x, y, w, h, kind="card", fill=fill)
        return shape

    def rule(self, name, x, y, w, thickness=0.012, color=RULE):
        from pptx.enum.shapes import MSO_SHAPE
        shape = self.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                                            Inches(w), Inches(thickness))
        shape.fill.solid()
        shape.fill.fore_color.rgb = rgb(color)
        shape.line.fill.background()
        shape.shadow.inherit = False
        self._record(name, x, y, w, thickness, kind="rule", fill=color)

    def picture(self, name, path, x, y, w):
        from PIL import Image
        with Image.open(path) as im:
            h = w * im.height / im.width
        self.slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w), Inches(h))
        self._record(name, x, y, w, h, kind="picture", src=path.name)
        return h

    def table(self, name, x, y, w, rows, col_widths, row_height=0.42, header_height=0.5):
        n_rows, n_cols = len(rows), len(rows[0])
        h = header_height + (n_rows - 1) * row_height
        shape = self.slide.shapes.add_table(n_rows, n_cols, Inches(x), Inches(y),
                                            Inches(w), Inches(h))
        tbl = shape.table
        tbl.first_row = True
        for i, frac in enumerate(col_widths):
            tbl.columns[i].width = Emu(int(Inches(w) * frac))
        tbl.rows[0].height = Inches(header_height)
        for r, row in enumerate(rows):
            if r:
                tbl.rows[r].height = Inches(row_height)
            for c, value in enumerate(row):
                cell = tbl.cell(r, c)
                cell.margin_left = cell.margin_right = Inches(0.1)
                cell.margin_top = cell.margin_bottom = Inches(0.03)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                cell.fill.solid()
                cell.fill.fore_color.rgb = rgb(PAPER if r % 2 else "F4F6F8")
                p = cell.text_frame.paragraphs[0]
                p.alignment = PP_ALIGN.LEFT if c == 0 else PP_ALIGN.RIGHT
                run = p.add_run()
                run.text = value
                f = run.font
                f.name = BODY
                f.size = Pt(16 if r else 15)
                f.bold = r == 0 or (r == len(rows) - 1)
                f.color.rgb = rgb(MUTED if r == 0 else INK)
        self._record(name, x, y, w, h, kind="table", rows=rows, col_widths=col_widths)
        return h


# ---- the layout ----------------------------------------------------------------------------

def build(p: Poster) -> None:
    """Place every element, in inches, on the 24x36 page.

    Two bands. The figures run down a wide left column with a narrow column of prose beside them,
    which keeps the photographs and the map large without letting either eat a third of the page.
    Below them the poster goes to two equal columns of text.
    """
    FIG = 15.2                       # width of the figure column
    SX = M + FIG + 0.7               # the narrow column beside the figures
    SW = W - M - SX
    y = M

    # --- title ---------------------------------------------------------------------------
    p.text("title", M, y, W - 2 * M, 1.6, C.TITLE, size=112, font=HEAD, bold=True, leading=0.92)
    y += 1.58
    p.text("subtitle", M, y, W - 2 * M - 1.4, 1.35, C.SUBTITLE, size=28, font=HEAD,
           color=MUTED, leading=1.2, italic=True)
    y += 1.38
    p.text("byline", M, y, W - 2 * M, 0.32, C.BYLINE, size=18, color=MUTED)
    y += 0.52
    p.rule("rule-title", M, y, W - 2 * M, 0.018, INK)
    y += 0.4

    # --- the numbers ---------------------------------------------------------------------
    gap, tile_h = 0.26, 1.34
    tile_w = (W - 2 * M - 3 * gap) / 4
    for i, (big, small) in enumerate(C.STATS):
        x = M + i * (tile_w + gap)
        p.card(f"stat-card-{i}", x, y, tile_w, tile_h)
        p.text(f"stat-big-{i}", x + 0.28, y + 0.15, tile_w - 0.56, 0.66, big,
               size=46, font=HEAD, bold=True, color=WARM, leading=1.0)
        p.text(f"stat-small-{i}", x + 0.28, y + 0.84, tile_w - 0.56, 0.42, small,
               size=14, color=MUTED, leading=1.1)
    y += tile_h + 0.5
    band = y                          # the prose column beside the figures starts here

    # --- the photographs -------------------------------------------------------------------
    p.text("grid-head", M, y, FIG, 0.44, C.GRID_CAPTION, size=26, font=HEAD, bold=True)
    y += 0.5
    cell = (FIG - 3 * 0.07) / 4
    rows = (([("Niger", "+1.93"), ("Nigeria", "+1.55"), ("Chad", "+1.46"), ("Mali", "+1.41")],
             WARM, "the four the model draws warmest", "warm-row.jpg"),
            ([("Norway", "\u22121.83"), ("Australia", "\u22121.73"),
              ("Costa Rica", "\u22121.39"), ("South Africa", "\u22121.38")],
             COOL, "the four it draws coolest", "cool-row.jpg"))
    for row, (labels, tone, caption, figure) in enumerate(rows):
        p.text(f"row-caption-{row}", M, y, FIG, 0.28,
               [(caption.upper(), {"color": tone, "bold": True})], size=14)
        y += 0.32
        for i, (name, value) in enumerate(labels):
            x = M + i * (cell + 0.07)
            p.text(f"label-{row}-{i}", x, y, cell, 0.3,
                   [(f"{name}  ", {"bold": True, "color": INK}), (value, {"color": tone, "bold": True})],
                   size=16, font=HEAD)
        y += 0.33
        y += p.picture(f"grid-row-{row}", FIGURES / figure, M, y, FIG) + (0.26 if row == 0 else 0)

    # prose beside the photographs
    sy = band
    p.text("question-head", SX, sy, SW, 0.4, "The question", size=24, font=HEAD, bold=True)
    sy += 0.46
    p.text("question-body", SX, sy, SW, 3.4, C.QUESTION, size=15, leading=1.3)
    sy += 3.5
    p.text("grid-note-head", SX, sy, SW, 0.36, "What you are looking at", size=19,
           font=HEAD, bold=True)
    sy += 0.42
    p.text("grid-note", SX, sy, SW, 3.6, C.GRID_NOTE, size=15, color=MUTED, leading=1.3)

    y += 0.55

    # --- the map, with the method in the column beside it --------------------------------
    p.text("map-head", M, y, FIG, 0.44, C.MAP_CAPTION, size=26, font=HEAD, bold=True)
    sy = y
    p.text("map-note", SX, sy + 0.04, SW, 1.2, C.MAP_NOTE, size=14.5, color=MUTED, leading=1.3)
    sy += 1.35
    p.text("method-head", SX, sy, SW, 0.4, "How it was measured", size=22, font=HEAD, bold=True)
    sy += 0.48
    for i, (head, body) in enumerate(C.METHOD):
        lines = 1 + (len(head) + len(body) + 2) // 42   # the narrow column wraps sooner
        p.text(f"method-{i}", SX, sy, SW, lines * 0.215 + 0.04,
               [(head + "  ", {"bold": True, "color": INK}), (body, {"color": MUTED})],
               size=13.5, leading=1.22)
        sy += lines * 0.215 + 0.16
    y += 0.5
    y += p.picture("map", FIGURES / "world-map.png", M, y, FIG)
    y = max(y, sy) + 0.5

    # --- table and findings ------------------------------------------------------------------
    left, right = M, M + COL + 0.9
    top = y
    p.text("table-head", left, y, COL, 0.44, C.TABLE_TITLE, size=26, font=HEAD, bold=True)
    y += 0.52
    y += p.table("table", left, y, COL, C.TABLE, [0.30, 0.11, 0.21, 0.19, 0.19],
                 row_height=0.38, header_height=0.44) + 0.2
    p.text("table-note", left, y, COL, 1.0, C.TABLE_NOTE, size=13.5, color=MUTED, leading=1.25)
    left_bottom = y + 0.95

    y = top
    p.text("find-head", right, y, COL, 0.44, "What it found", size=26, font=HEAD, bold=True)
    y += 0.52
    for i, (head, body) in enumerate(C.FINDINGS):
        lines = 1 + len(body) // 86
        p.text(f"find-{i}-n", right, y + 0.02, 0.4, 0.34, f"{i + 1}",
               size=18, font=HEAD, bold=True, color=WARM)
        p.text(f"find-{i}-h", right + 0.42, y, COL - 0.42, 0.3, head, size=17,
               font=HEAD, bold=True)
        p.text(f"find-{i}-b", right + 0.42, y + 0.33, COL - 0.42, lines * 0.23 + 0.04, body,
               size=14.5, color=MUTED, leading=1.25)
        y += 0.33 + lines * 0.23 + 0.26
    right_bottom = y

    # --- what it cannot show, across the foot in two columns ---------------------------------
    y = max(left_bottom, right_bottom) + 0.25
    p.rule("rule-foot", M, y, W - 2 * M, 0.012)
    y += 0.36
    p.text("limits-head", M, y, W - 2 * M, 0.42, "What it cannot show", size=24,
           font=HEAD, bold=True)
    y += 0.5
    half = (len(C.LIMITS) + 1) // 2
    my = ly = y
    for i, item in enumerate(C.LIMITS):
        column, cy = (left, my) if i < half else (right, ly)
        lines = 1 + len(item) // 84
        p.text(f"limit-{i}-dot", column, cy + 0.02, 0.18, 0.26, "\u2022", size=15,
               color=WARM, bold=True)
        p.text(f"limit-{i}", column + 0.24, cy, COL - 0.24, lines * 0.225 + 0.04, item,
               size=14, color=MUTED, leading=1.25)
        if i < half:
            my += lines * 0.225 + 0.17
        else:
            ly += lines * 0.225 + 0.17

    y = max(my, ly) + 0.3
    p.rule("rule-end", M, y, W - 2 * M, 0.012)
    p.text("footer", M, y + 0.2, W - 2 * M, 0.36, C.FOOTER, size=14, color=MUTED)
    p.bottom = y + 0.56


# ---- checks -------------------------------------------------------------------------------

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
    want("low income, controlled", net["income"]["Low income"]["d"], 0.52, tol=0.03)
    want("Africa, controlled", net["region"]["Africa"]["d"], -0.03, tol=0.03)
    want("Asia, controlled", net["region"]["Asia"]["d"], 0.73, tol=0.04)
    raw = r["groups"]
    want("low income, raw", raw["income"]["Low income"]["d"], 0.72, tol=0.03)
    want("Asia, raw", raw["region"]["Asia"]["d"], 0.60, tol=0.03)

    total = sum(1 for _ in (ROOT / "outputs").glob("phase2-*/images/*/*/*.jpg"))
    if total != 61488:
        problems.append(f"61,488 images: disk has {total:,}")
    return problems


def check_layout(p: Poster) -> list[str]:
    """Nothing off the page, nothing on top of anything else, nothing inside the margin."""
    problems = []
    for b in p.boxes:
        if b["x"] < M - 0.02 or b["x"] + b["w"] > W - M + 0.02:
            problems.append(f"{b['name']} breaks the side margin "
                            f"(x {b['x']:.2f}..{b['x'] + b['w']:.2f})")
        if b["y"] < M - 0.02 or b["y"] + b["h"] > H - 0.5:
            problems.append(f"{b['name']} runs off the page "
                            f"(y {b['y']:.2f}..{b['y'] + b['h']:.2f})")
    # Text and pictures may not overlap; cards are backdrops and are allowed under their contents.
    solid = [b for b in p.boxes if not b["name"].startswith(("stat-card", "rule"))]
    for i, a in enumerate(solid):
        for b in solid[i + 1:]:
            dx = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
            dy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
            if dx > 0.04 and dy > 0.04:
                problems.append(f"{a['name']} overlaps {b['name']} "
                                f"by {dx:.2f}x{dy:.2f} in")
    return problems


# ---- the HTML proof -----------------------------------------------------------------------

PX = 34  # pixels per inch in the proof


def write_proof(p: Poster) -> Path:
    """Draw the same boxes, with the same words at the same sizes, so the layout can be looked at.

    This machine has no LibreOffice to turn the .pptx back into an image, so without this the
    poster would ship unseen. Both outputs read the one list of boxes, so the geometry here is the
    geometry the .pptx got. Fonts are the real ones where the browser has them, which makes text
    overflow visible -- the defect worth catching before a 24x36 sheet goes to a printer.
    """
    def px(inches): return f"{inches * PX:.1f}px"
    def pt(points): return f"{points / 72 * PX:.2f}px"

    parts = []
    for b in p.boxes:
        pos = (f"left:{px(b['x'])};top:{px(b['y'])};width:{px(b['w'])};height:{px(b['h'])}")
        kind = b.get("kind", "text")
        if kind == "rule":
            parts.append(f'<div class="rule" style="{pos};background:#{b["fill"]}"></div>')
        elif kind == "card":
            parts.append(f'<div class="card" style="{pos};background:#{b["fill"]}"></div>')
        elif kind == "picture":
            parts.append(f'<div class="pic" style="{pos}">'
                         f'<img src="{b["src"]}" alt=""></div>')
        elif kind == "table":
            cells = []
            for r, row in enumerate(b["rows"]):
                tds = "".join(
                    f'<td style="width:{w * 100:.1f}%;text-align:{"left" if c == 0 else "right"};'
                    f'font-weight:{700 if r == 0 or r == len(b["rows"]) - 1 else 400};'
                    f'color:#{MUTED if r == 0 else INK};'
                    f'background:#{"F4F6F8" if r % 2 == 0 else PAPER};'
                    f'font-size:{pt(16 if r else 15)}">{v}</td>'
                    for c, (v, w) in enumerate(zip(row, b["col_widths"])))
                cells.append(f"<tr>{tds}</tr>")
            parts.append(f'<div class="tbl" style="{pos}"><table>{"".join(cells)}</table></div>')
        else:
            ALIGN = {"l": "left", "c": "center", "r": "right"}
            runs = "".join(
                f'<p style="font-family:{o["font"]},serif;font-size:{pt(o["size"])};'
                f'font-weight:{700 if o["bold"] else 400};'
                f'font-style:{"italic" if o["italic"] else "normal"};'
                f'color:#{o["color"]};line-height:{o["leading"]};'
                f'text-align:{ALIGN[o["align"]]}">{t}</p>'
                for t, o in b["runs"])
            align = {"t": "flex-start", "m": "center", "b": "flex-end"}[b.get("anchor", "t")]
            parts.append(f'<div class="txt" style="{pos};justify-content:{align}" '
                         f'data-name="{b["name"]}">{runs}</div>')

    PROOF.parent.mkdir(parents=True, exist_ok=True)
    PROOF.write_text(f"""<!doctype html><meta charset="utf-8"><title>Poster proof</title>
<style>
 body {{ margin:24px; background:#5a6069; font-family:Calibri,sans-serif; }}
 .page {{ position:relative; width:{px(W)}; height:{px(H)}; background:#{PAPER};
          box-shadow:0 2px 40px rgba(0,0,0,.55); overflow:hidden; }}
 .page > div {{ position:absolute; box-sizing:border-box; }}
 .txt {{ display:flex; flex-direction:column; overflow:visible; }}
 .txt p {{ margin:0; }}
 .pic img {{ width:100%; height:100%; object-fit:fill; display:block; }}
 .tbl table {{ width:100%; border-collapse:collapse; table-layout:fixed; }}
 .tbl td {{ padding:{px(0.03)} {px(0.1)}; font-family:Calibri,sans-serif; }}
 .guide {{ position:absolute; inset:{px(M)} {px(M)} {px(0.8)} {px(M)};
           outline:1px dashed rgba(200,80,80,.35); pointer-events:none; }}
</style>
<div class="page">{''.join(parts)}<div class="guide"></div></div>
<p style="color:#e6e9ee;font-size:13px">{len(p.boxes)} elements \u00b7 {W:g}in \u00d7 {H:g}in
 \u00b7 content ends at {getattr(p, 'bottom', 0):.2f}in \u00b7 proof at {PX}px/in</p>""",
                     encoding="utf-8")
    return PROOF


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the poster.")
    ap.add_argument("--check", action="store_true", help="verify the numbers and layout, write nothing")
    args = ap.parse_args()

    numbers = check_numbers()
    poster = Poster()
    build(poster)
    layout = check_layout(poster)

    for label, found in (("numbers", numbers), ("layout", layout)):
        print(f"  {label}: {'OK' if not found else str(len(found)) + ' problem(s)'}")
        for item in found:
            print(f"    - {item}")
    if args.check:
        sys.exit(1 if numbers or layout else 0)
    if numbers:
        sys.exit("\nRefusing to build: the poster's numbers no longer match the run.")

    poster.prs.save(OUT)
    proof = write_proof(poster)
    print(f"\n  {OUT.relative_to(ROOT)}  {OUT.stat().st_size / 1e6:.1f} MB  "
          f"({W:g}in x {H:g}in)")
    print(f"  {proof.relative_to(ROOT)}  (open it to look at the layout)")
    print(f"  content ends at {poster.bottom:.2f}in of {H:g}in")


if __name__ == "__main__":
    main()
