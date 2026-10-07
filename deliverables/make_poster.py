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

# Poster type, not slide type. A 24x36 sheet is read from three or four feet, where the rule of
# thumb is that a point size is comfortable from about size/6 feet away: 24pt at four feet, 40pt at
# nearly seven. Conference guidance puts body text at 24pt and headings at 36pt or more. The first
# draft of this poster used a slide deck's sizes -- body 14pt -- on a page 1.8 times a slide's
# width, which left 92% of its characters below the floor and unreadable at any sane distance.
# check_type() below fails the build if that happens again.
T = {
    "title": 84,      # readable across a room
    "subtitle": 34,
    "byline": 22,
    "stat": 52,
    "stat-label": 21,
    "section": 36,     # the headline of each block
    "sub": 26,         # headings inside a column
    "body": 24,        # the floor for anything a reader is meant to read
    "note": 21,       # captions and asides, glanced at from closer
    "detail": 23,      # secondary prose a reader actually reads: findings, method, limits        # captions and asides, read closer
    "table": 23,
    "label": 25,
}
TYPE_FLOOR = 21        # nothing on the poster may be smaller


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

    def bars(self, name, x, y, w, items, *, label_w=3.5, row_h=0.56, gap=0.14):
        """Horizontal bars with their labels, for comparing a handful of magnitudes."""
        from pptx.enum.shapes import MSO_SHAPE
        longest = max(v for _, v in items)
        for i, (label, value) in enumerate(items):
            cy = y + i * (row_h + gap)
            p_w = (w - label_w - 1.4) * value / longest
            self.text(f"{name}-label-{i}", x, cy + 0.08, label_w, row_h - 0.16, label,
                      size=T["detail"], color=INK)
            track = self.slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x + label_w), Inches(cy + 0.06),
                Inches(max(p_w, 0.1)), Inches(row_h - 0.2))
            track.adjustments[0] = 0.3
            track.fill.solid()
            track.fill.fore_color.rgb = rgb(WARM if i == 0 else "C9B68A")
            track.line.fill.background()
            track.shadow.inherit = False
            self._record(f"{name}-bar-{i}", x + label_w, cy + 0.06, max(p_w, 0.1), row_h - 0.2,
                         kind="card", fill=WARM if i == 0 else "C9B68A")
            self.text(f"{name}-value-{i}", x + label_w + p_w + 0.16, cy + 0.04, 1.2, row_h - 0.1,
                      f"{value}%", size=T["sub"], font=HEAD, bold=True,
                      color=WARM if i == 0 else MUTED)
        return len(items) * (row_h + gap) - gap

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

def wrapped(text: str, width_in: float, size_pt: float, *, bold=False) -> float:
    """Roughly how tall `text` will be once it wraps, in inches.

    Calibri averages about 0.47 of its point size per character, a little more when bold. This only
    has to be close: check_layout asserts the result does not collide with anything, and the proof
    renders the real thing.
    """
    per_char = size_pt * (0.50 if bold else 0.47) / 72
    lines = max(1, -(-int(len(text) * per_char / width_in * 100) // 100))
    return lines * size_pt / 72 * 1.3


def build(p: Poster) -> None:
    """Place every element, in inches, on the 24x36 page.

    The poster is a story in five beats -- the problem, how we looked, what we found, what it
    means, what is next -- so the bands run in that order down the page and each one is announced
    by a heading a passer-by can read from across the room.
    """
    FIG = 9.8                       # the figure column
    SX = M + FIG + 0.7               # the prose column beside it
    SW = W - M - SX
    y = M

    def section(label, at, width=W - 2 * M, name=None):
        """A band heading. Returns the y to carry on from."""
        h = wrapped(label, width, T["section"], bold=True)
        p.text(name or f"head-{label[:12]}", M, at, width, h, label,
               size=T["section"], font=HEAD, bold=True)
        return at + h + 0.14

    # --- title ---------------------------------------------------------------------------
    p.text("title", M, y, W - 2 * M, 1.2, C.TITLE, size=T["title"], font=HEAD, bold=True,
           leading=0.92)
    y += 1.24
    p.text("subtitle", M, y, W - 2 * M - 0.6, wrapped(C.SUBTITLE, W - 2 * M - 0.6, T["subtitle"]),
           C.SUBTITLE, size=T["subtitle"], font=HEAD, color=MUTED, leading=1.18, italic=True)
    y += wrapped(C.SUBTITLE, W - 2 * M - 0.6, T["subtitle"]) + 0.12
    p.text("byline", M, y, W - 2 * M, 0.38, C.BYLINE, size=T["byline"], color=MUTED)
    y += 0.5
    p.rule("rule-title", M, y, W - 2 * M, 0.02, INK)
    y += 0.34

    # --- the numbers ---------------------------------------------------------------------
    gap, tile_h = 0.26, 1.22
    tile_w = (W - 2 * M - 3 * gap) / 4
    for i, (big, small) in enumerate(C.STATS):
        x = M + i * (tile_w + gap)
        p.card(f"stat-card-{i}", x, y, tile_w, tile_h)
        p.text(f"stat-big-{i}", x + 0.32, y + 0.13, tile_w - 0.64, 0.63, big,
               size=T["stat"], font=HEAD, bold=True, color=WARM, leading=1.0)
        p.text(f"stat-small-{i}", x + 0.32, y + 0.78, tile_w - 0.64, 0.56, small,
               size=T["stat-label"], color=MUTED, leading=1.15)
    y += tile_h + 0.34

    # --- 1. the problem --------------------------------------------------------------------
    y = section(C.PROBLEM_HEAD, y, name="problem-head")
    halves = C.PROBLEM.split("\n\n")
    ph = max(wrapped(t, COL, T["body"]) for t in halves)
    for i, (text, x) in enumerate(zip(halves, (M, M + COL + 0.9))):
        p.text(f"problem-{i}", x, y, COL, ph, text, size=T["body"], leading=1.3)
    y += ph + 0.36

    # --- 2. how we looked -------------------------------------------------------------------
    y = section(C.PROCESS_HEAD, y, name="process-head")
    step_gap = 0.3
    step_w = (W - 2 * M - 4 * step_gap) / 5
    step_h = 0.0
    for i, (head, body) in enumerate(C.PROCESS):
        x = M + i * (step_w + step_gap)
        hh = wrapped(head, step_w - 0.55, T["sub"], bold=True)
        bh = wrapped(body, step_w, T["note"])
        p.text(f"step-{i}-n", x, y + 0.02, 0.5, 0.44, f"{i + 1}", size=T["sub"], font=HEAD,
               bold=True, color=WARM)
        p.text(f"step-{i}-h", x + 0.55, y, step_w - 0.55, hh, head, size=T["sub"],
               font=HEAD, bold=True)
        p.text(f"step-{i}-b", x, y + max(hh, 0.44) + 0.12, step_w, bh, body,
               size=T["note"], color=MUTED, leading=1.28)
        step_h = max(step_h, max(hh, 0.44) + 0.12 + bh)
    y += step_h + 0.36

    # --- 3. what we found --------------------------------------------------------------------
    y = section(C.FINDINGS_HEAD, y, name="findings-head")

    # the photographs: the two strips side by side, so eight pictures read as one row and the
    # images come out larger than stacking them did
    gh = wrapped(C.GRID_CAPTION, W - 2 * M, T["sub"], bold=True)
    p.text("grid-head", M, y, W - 2 * M, gh, C.GRID_CAPTION, size=T["sub"], font=HEAD, bold=True)
    y += gh + 0.12
    strip = (W - 2 * M - 0.5) / 2
    cell = (strip - 3 * 0.07) / 4
    groups = (("the four it draws warmest", WARM, "warm-row.jpg", M,
               [("Niger", "+1.93"), ("Nigeria", "+1.55"), ("Chad", "+1.46"), ("Mali", "+1.41")]),
              ("the four it draws coolest", COOL, "cool-row.jpg", M + strip + 0.5,
               [("Norway", "\u22121.83"), ("Australia", "\u22121.73"),
                ("Costa Rica", "\u22121.39"), ("South Africa", "\u22121.38")]))
    for g, (caption, tone, figure, x0, labels) in enumerate(groups):
        p.text(f"row-caption-{g}", x0, y, strip, 0.34,
               [(caption.upper(), {"color": tone, "bold": True})], size=T["note"])
        for i, (name, value) in enumerate(labels):
            x = x0 + i * (cell + 0.07)
            p.text(f"label-{g}-{i}", x, y + 0.38, cell, 0.4,
                   [(f"{name} ", {"bold": True, "color": INK}), (value, {"color": tone, "bold": True})],
                   size=T["label"], font=HEAD)
        img_h = p.picture(f"grid-row-{g}", FIGURES / figure, x0, y + 0.78, strip)
    y += 0.78 + img_h + 0.18
    nh = wrapped(C.GRID_NOTE, W - 2 * M, T["note"])
    p.text("grid-note", M, y, W - 2 * M, nh,
           [(C.GRID_NOTE_HEAD + "  ", {"bold": True, "color": INK}), (C.GRID_NOTE, {"color": MUTED})],
           size=T["note"], leading=1.28)
    y += nh + 0.34

    # the findings themselves, full width in two columns -- the same words in a narrow column
    # run two inches taller for no gain
    left, right = M, M + COL + 0.9
    fy = gy = y
    for i, (head, body) in enumerate(C.FINDINGS):
        column, cy = (left, fy) if i % 2 == 0 else (right, gy)
        hh = wrapped(head, COL - 0.5, T["sub"], bold=True)
        bh = wrapped(body, COL - 0.5, T["detail"])
        p.text(f"find-{i}-n", column, cy + 0.03, 0.42, 0.42, "\u25cf", size=T["note"], color=WARM)
        p.text(f"find-{i}-h", column + 0.5, cy, COL - 0.5, hh, head, size=T["sub"],
               font=HEAD, bold=True)
        p.text(f"find-{i}-b", column + 0.5, cy + hh + 0.06, COL - 0.5, bh, body,
               size=T["detail"], color=MUTED, leading=1.28)
        if i % 2 == 0:
            fy += hh + bh + 0.3
        else:
            gy += hh + bh + 0.3
    y = max(fy, gy) + 0.3

    # the map in one column, what accounts for the warmth in the other
    left, right = M, M + COL + 0.9
    mh = wrapped(C.MAP_CAPTION, COL, T["sub"], bold=True)
    p.text("map-head", left, y, COL, mh, C.MAP_CAPTION, size=T["sub"], font=HEAD, bold=True)
    map_w = COL - 1.1   # the map is wider than it is tall; it does not need the whole column
    map_h = p.picture("map", FIGURES / "world-map.png", left, y + mh + 0.12, map_w)
    nh = wrapped(C.MAP_NOTE, COL, T["note"])
    p.text("map-note", left, y + mh + 0.18 + map_h, COL, nh, C.MAP_NOTE,
           size=T["note"], color=MUTED, leading=1.28)
    map_bottom = y + mh + 0.18 + map_h + nh

    sy = y
    p.text("explains-head", right, sy, COL, mh, C.EXPLAINS_HEAD, size=T["sub"],
           font=HEAD, bold=True)
    sy += mh + 0.2
    sy += p.bars("explains", right, sy, COL, C.EXPLAINS, label_w=4.2) + 0.24
    eh = wrapped(C.EXPLAINS_NOTE, COL, T["note"])
    p.text("explains-note", right, sy, COL, eh, C.EXPLAINS_NOTE, size=T["note"],
           color=MUTED, leading=1.28)
    y = max(map_bottom, sy + eh) + 0.32

    # --- 4. what it means ---------------------------------------------------------------------
    p.rule("rule-means", M, y - 0.26, W - 2 * M, 0.014)
    y = section(C.MEANS_HEAD, y, name="means-head")
    left, right = M, M + COL + 0.9
    my = ly = y
    for i, (head, body) in enumerate(C.MEANS):
        column, cy = (left, my) if i % 2 == 0 else (right, ly)
        hh = wrapped(head, COL - 0.5, T["sub"], bold=True)
        bh = wrapped(body, COL - 0.5, T["detail"])
        p.text(f"means-{i}-n", column, cy + 0.03, 0.42, 0.42, "\u25cf", size=T["note"], color=WARM)
        p.text(f"means-{i}-h", column + 0.5, cy, COL - 0.5, hh, head, size=T["sub"],
               font=HEAD, bold=True)
        p.text(f"means-{i}-b", column + 0.5, cy + hh + 0.06, COL - 0.5, bh, body,
               size=T["detail"], color=MUTED, leading=1.28)
        if i % 2 == 0:
            my += hh + bh + 0.26
        else:
            ly += hh + bh + 0.26
    y = max(my, ly) + 0.18

    # --- 5. what is next ----------------------------------------------------------------------
    p.rule("rule-next", M, y - 0.1, W - 2 * M, 0.014)
    y = section(C.NEXT_HEAD, y + 0.04, width=COL, name="next-head")
    p.text("limits-head", right, y - wrapped(C.NEXT_HEAD, COL, T["section"], bold=True) - 0.22,
           COL, wrapped(C.LIMITS_HEAD, COL, T["section"], bold=True), C.LIMITS_HEAD,
           size=T["section"], font=HEAD, bold=True)
    ny = y
    for i, item in enumerate(C.NEXT):
        h = wrapped(item, COL - 0.5, T["detail"])
        p.text(f"next-{i}-n", left, ny + 0.03, 0.42, 0.42, "\u25cf", size=T["note"], color=WARM)
        p.text(f"next-{i}", left + 0.5, ny, COL - 0.5, h, item, size=T["detail"], leading=1.28)
        ny += h + 0.14
    lh = wrapped(C.LIMITS, COL, T["detail"])
    p.text("limits", right, y, COL, lh, C.LIMITS, size=T["detail"], color=MUTED, leading=1.28)

    y = max(ny, y + lh) + 0.24
    p.rule("rule-end", M, y, W - 2 * M, 0.014)
    p.text("footer", M, y + 0.18, W - 2 * M, 0.42, C.FOOTER, size=T["byline"], color=MUTED)
    p.bottom = y + 0.62


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


def check_type(p: Poster) -> list[str]:
    """Nothing on the poster may be set below the floor a reader can take in standing up.

    The first draft of this poster was built with a slide deck's type sizes and left 92% of its
    characters under 24pt -- comfortable only with your nose against the sheet. This is the guard
    against repeating that.
    """
    problems = []
    for b in p.boxes:
        if b.get("kind") == "text":
            for text, o in b["runs"]:
                if o["size"] < TYPE_FLOOR:
                    problems.append(f"{b['name']} is {o['size']}pt, below the {TYPE_FLOOR}pt floor "
                                    f"(readable only from {o['size'] / 6:.1f} ft)")
        elif b.get("kind") == "table" and T["table"] < TYPE_FLOOR:
            problems.append(f"{b['name']} is {T['table']}pt, below the {TYPE_FLOOR}pt floor")
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
    typography = check_type(poster)

    for label, found in (("numbers", numbers), ("layout", layout), ("type", typography)):
        print(f"  {label}: {'OK' if not found else str(len(found)) + ' problem(s)'}")
        for item in found:
            print(f"    - {item}")
    if args.check:
        sys.exit(1 if numbers or layout or typography else 0)
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
