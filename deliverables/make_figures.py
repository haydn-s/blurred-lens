"""Build the poster's figures at print resolution.

    python -m deliverables.make_figures

Writes PNGs into deliverables/figures/. Everything here is drawn from the run's own output, so
re-running after a new run refreshes the poster's art rather than leaving it stale.

The world map is drawn here rather than screenshotted from the website for two reasons: a printed
reader cannot rotate a globe, so half the countries would be hidden; and a browser screenshot tops
out near a thousand pixels, where a 24-inch poster at 300 DPI wants several thousand.
"""

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

from blurred_lens.config import ROOT, load_config, run_dir
from blurred_lens.report import build_report

HERE = Path(__file__).resolve().parent
FIGURES = HERE / "figures"
SHAPES = HERE / ".countries-50m.json"
DPI = 300

# The site's scale, repeated so the poster and the globe cannot disagree (web/js/globe.js SCALE).
BREAKS = [-1.5, -0.9, -0.3, 0.3, 0.9, 1.5]
COLORS = ["#6abcff", "#649fe0", "#6283a6", "#6d6c67", "#957c53", "#c2923f", "#eca92e"]
# Printed on white, not on the website's near-black, so the unmeasured land and the borders are
# the light-background equivalents rather than the screen ones.
NO_DATA = "#e4e6ea"
BORDER = "#ffffff"
SEA = "#f7f8fa"


# Shapes the map carries without a numeric code, drawn as part of the country they sit in -- the
# same aliases the website uses (web/js/data.js SHAPE_ALIASES).
SHAPE_ALIASES = {"somaliland": "SOM", "n. cyprus": "CYP"}


def decode(topology: dict) -> dict[str, list[list[tuple[float, float]]]]:
    """TopoJSON -> {key: [ring, ...]} in lon/lat degrees, keyed by numeric id or `name:<name>`."""
    sx, sy = topology["transform"]["scale"]
    tx, ty = topology["transform"]["translate"]
    arcs = []
    for arc in topology["arcs"]:
        x = y = 0
        points = []
        for dx, dy in arc:
            x, y = x + dx, y + dy
            points.append((x * sx + tx, y * sy + ty))
        arcs.append(points)

    def ring(indices):
        out = []
        for i in indices:
            part = arcs[~i][::-1] if i < 0 else arcs[i]
            out.extend(part if not out else part[1:])
        return out

    shapes = {}
    for geom in topology["objects"]["countries"]["geometries"]:
        polygons = (geom["arcs"] if geom["type"] == "MultiPolygon" else [geom["arcs"]])
        rings = [ring(r) for polygon in polygons for r in polygon]
        key = (str(geom["id"]).zfill(3) if "id" in geom
               else "name:" + geom.get("properties", {}).get("name", "?").lower())
        shapes[key] = rings
    return shapes


def robinson(lon: float, lat: float) -> tuple[float, float]:
    """Robinson projection: rounder than equirectangular and kinder to the high latitudes."""
    X = [1.0000,0.9986,0.9954,0.9900,0.9822,0.9730,0.9600,0.9427,0.9216,0.8962,
         0.8679,0.8350,0.7986,0.7597,0.7186,0.6732,0.6213,0.5722,0.5322]
    Y = [0.0000,0.0620,0.1240,0.1860,0.2480,0.3100,0.3720,0.4340,0.4958,0.5571,
         0.6176,0.6769,0.7346,0.7903,0.8435,0.8936,0.9394,0.9761,1.0000]
    a = min(abs(lat), 89.999) / 5.0
    i = min(int(a), 17)
    f = a - i
    x = (X[i] + (X[i + 1] - X[i]) * f) * lon / 180.0
    y = (Y[i] + (Y[i + 1] - Y[i]) * f) * (1 if lat >= 0 else -1)
    return x, y


ROBINSON_RATIO = (0.8487 * math.pi) / 1.3523  # 1.9719: the projection's width-to-height
LATITUDE_RANGE = (-57.0, 84.0)  # Tierra del Fuego to northern Greenland


def split_at_dateline(ring: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """Cut a ring wherever it jumps the antimeridian.

    Russia's eastern tip and Fiji carry points on both sides of 180 degrees. Projected as one
    polygon those jump the full width of the map and paint a band straight across the Arctic, so
    each crossing starts a new piece.
    """
    pieces, current = [], []
    for point in ring:
        if current and abs(point[0] - current[-1][0]) > 180:
            pieces.append(current)
            current = []
        current.append(point)
    pieces.append(current)
    return [piece for piece in pieces if len(piece) >= 3]


def bucket(index: float) -> str:
    return COLORS[len([e for e in BREAKS if index >= e])]


def draw_map(tint: dict[str, float], width_in: float, out: Path) -> Path:
    """A Robinson choropleth, `tint` keyed by the map's own numeric country ids."""
    width = int(width_in * DPI)
    # Robinson's own proportions: half-width 0.8487*pi against half-height 1.3523, so the whole
    # map is 1.9719 times as wide as it is tall. `robinson` already returns both axes on -1..1,
    # so the only thing left is to scale each to the canvas.
    height = int(round(width / ROBINSON_RATIO))
    img = Image.new("RGB", (width, height), SEA)
    pen = ImageDraw.Draw(img)

    def place(lon, lat):
        x, y = robinson(lon, lat)
        return (width / 2 + x * width / 2, height / 2 - y * height / 2)

    for numeric, rings in decode(json.loads(SHAPES.read_text())).items():
        fill = bucket(tint[numeric]) if numeric in tint else NO_DATA
        for r in rings:
            for piece in split_at_dateline(r):
                pen.polygon([place(lon, lat) for lon, lat in piece], fill=fill,
                            outline=BORDER, width=2)
    # Crop to the inhabited latitudes: Antarctica and the empty Arctic ocean are a distraction on
    # a poster about where people live, and they cost an inch of poster each.
    top = place(0, LATITUDE_RANGE[1])[1]
    bottom = place(0, LATITUDE_RANGE[0])[1]
    img = img.crop((0, int(top), width, int(bottom)))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, dpi=(DPI, DPI))
    return out


def image_grid(run: str, groups: list[list[str]], place: str, index: int, out: Path) -> Path:
    """A grid of generated images: one row per group, one column per country.

    Every country's image `index` was generated from the same seed, so these pictures start from
    the same noise and the street recedes identically in all of them. The only thing that differs
    between one cell and the next is the country named in the sentence -- which is what makes the
    colour difference worth looking at rather than a coincidence of framing.
    """
    # Cropped to 3:2 rather than left square. On a poster a square strip costs half an inch of
    # page per column for sky and tarmac that carry the same cast as the middle of the frame, and
    # the page is the scarce thing. Centre-cropped, so the horizon stays where the camera put it.
    cell_w, cell_h, gutter = 1024, 683, 14
    cols = max(len(g) for g in groups)
    width = cols * cell_w + (cols - 1) * gutter
    height = len(groups) * cell_h + (len(groups) - 1) * gutter
    sheet = Image.new("RGB", (width, height), "white")
    for row, group in enumerate(groups):
        for col, iso3 in enumerate(group):
            source = ROOT / "outputs" / run / "images" / iso3 / place / f"{index:04d}.jpg"
            with Image.open(source) as im:
                top = (im.height - cell_h) // 2
                tile = im.crop((0, top, cell_w, top + cell_h))
                sheet.paste(tile, (col * (cell_w + gutter), row * (cell_h + gutter)))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=95, dpi=(DPI, DPI))
    return out


def main() -> None:
    cfg = load_config()
    report = build_report(cfg, run_dir(cfg, "phase2-noon"), "cast_b", permutations=2000,
                          baseline_dir=run_dir(cfg, "phase2-baseline-noon"))
    numeric = {c["iso_a3"]: c["iso_num"] for c in json.loads((ROOT / "data/countries.json").read_text())}
    index = {iso3: d["index"] for iso3, d in report["countries"].items()}
    tint = {numeric[iso3]: v for iso3, v in index.items() if numeric.get(iso3)}
    # Shapes with no code of their own take the colour of the country they belong to.
    tint.update({f"name:{name}": index[iso3] for name, iso3 in SHAPE_ALIASES.items() if iso3 in index})
    path = draw_map(tint, width_in=20.0, out=FIGURES / "world-map.png")
    with Image.open(path) as im:
        print(f"  {path.relative_to(ROOT)}  {im.width}x{im.height}px  "
              f"{path.stat().st_size / 1e6:.1f} MB · {len(tint)} countries tinted")

    ranked = sorted(report["countries"].items(), key=lambda kv: -kv[1]["index"])
    warm = [iso3 for iso3, _ in ranked[:4]]
    cool = [iso3 for iso3, _ in ranked[-4:]][::-1]
    # Two separate strips rather than one block, so the poster can name the countries between them.
    for label, group in (("warm-row", warm), ("cool-row", cool)):
        path = image_grid("phase2-noon", [group], "city", 1, FIGURES / f"{label}.jpg")
        with Image.open(path) as im:
            print(f"  {path.relative_to(ROOT)}  {im.width}x{im.height}px  "
                  f"{path.stat().st_size / 1e6:.1f} MB  "
                  f"({', '.join(report['countries'][i]['name'] for i in group)})")


if __name__ == "__main__":
    main()
