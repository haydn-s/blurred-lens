"""Compare countries: does the model grade some of them warmer, dustier or darker than others?

    python -m blurred_lens.report                  # the headline metric from config.toml
    python -m blurred_lens.report --metric haze    # rank by something else
    python -m blurred_lens.report --run poc-event

Reads what blurred_lens.analyze measured and answers one question at a time: for the same kind of
place, how far from the middle does each country sit, and do those distances line up with region or
income rather than with geography?

Two rules keep the comparison honest. Countries are compared within a place -- a city against other
countries' cities, never against farms -- because place types differ in color for reasons that have
nothing to do with the country. And the country, not the image, is the unit of comparison: 500
images of one prompt say precisely what that one answer looks like, not that the answer is common,
so the group tests below shuffle country labels rather than image labels.

What this can and cannot show: with the prompt, the camera view, the model and the size all fixed,
the country name is the only thing that changes between two prompts for the same place. A gap here
is therefore caused by the country name. Whether the model is wrong to draw Lagos warmer than Oslo
is a separate question this cannot answer -- but a gap that tracks income rather than latitude is
the shape of the claim the media-studies literature makes about the yellow filter.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .analyze import analysis_path
from .config import ROOT, load_config, run_dir
from .prompts import load_json

# How to read each measurement, for the header line of the printed table.
LABELS = {
    "cast_b": "yellow-blue cast (higher is more yellow)",
    "cast_a": "green-red cast (higher is more red)",
    "cast_kelvin": "color temperature in kelvin (lower is warmer)",
    "midtone_b": "yellow-blue lean of the mid-tones (higher is more yellow)",
    "b": "yellow-blue average of every pixel (higher is more yellow)",
    "haze": "haze from the dark channel (higher is dustier)",
    "lightness": "average lightness (lower is darker)",
    "contrast": "contrast (lower is flatter)",
    "colorfulness": "colorfulness (higher is more vivid)",
    "chroma": "average saturation (higher is more saturated)",
    "amber_share": "share of the frame in amber hues",
    "cool_share": "share of the frame in cool hues",
    "green_share": "share of the frame in greens",
    "warm_split": "warm highlights against cool shadows (near zero means one flat cast)",
    "edge_density": "how busy the frame is",
    "sky_b": "yellow-blue cast of the sky strip (higher is more yellow)",
    "sky_lightness": "lightness of the sky strip",
}


def load_summaries(out: Path) -> dict[tuple[str, str], dict]:
    """Every prompt's measurements for this run, keyed by (country, place)."""
    index_path = out / "analysis" / "index.json"
    if not index_path.exists():
        raise SystemExit(f"No measurements in {out / 'analysis'}. Run `python -m blurred_lens.analyze` first.")
    summaries = {}
    for key in json.loads(index_path.read_text()):
        iso3, place = key.split("/", 1)
        path = analysis_path(out, iso3, place)
        if path.exists():
            summaries[(iso3, place)] = json.loads(path.read_text())
    return summaries


def cohens_d(a: np.ndarray, b: np.ndarray) -> float | None:
    """Effect size: the gap between two groups in pooled standard deviations."""
    if len(a) < 2 or len(b) < 2:
        return None
    pooled = np.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2))
    return float((a.mean() - b.mean()) / pooled) if pooled > 0 else None


def permutation_p(a: np.ndarray, b: np.ndarray, permutations: int, seed: int = 0) -> float | None:
    """How often shuffling the labels separates the groups as far as the real labels do.

    With a dozen countries there is no room for an asymptotic test, and this makes no assumption
    about the shape of the distribution.
    """
    if len(a) < 2 or len(b) < 2:
        return None
    rng = np.random.default_rng(seed)
    pool = np.concatenate([a, b])
    observed = abs(a.mean() - b.mean())
    extreme = 0
    for _ in range(permutations):
        rng.shuffle(pool)
        if abs(pool[:len(a)].mean() - pool[len(a):].mean()) >= observed - 1e-12:
            extreme += 1
    return float((extreme + 1) / (permutations + 1))


def place_standings(summaries: dict, metric: str) -> dict[str, dict]:
    """For each place: every country's mean, and how far from the middle it sits.

    The z-score's yardstick is how much countries differ from each other, so "+1.5" reads as one and
    a half country-to-country standard deviations above the average country.
    """
    standings = {}
    for place in sorted({place for _, place in summaries}):
        means, noise = {}, {}
        for (iso3, p), data in summaries.items():
            if p == place and metric in data.get("summary", {}):
                means[iso3] = data["summary"][metric]["mean"]
                noise[iso3] = data["summary"][metric]["sem"]
        if len(means) < 3:  # fewer than three countries and "far from the middle" means nothing
            continue
        values = np.array(list(means.values()))
        spread = float(values.std(ddof=1))
        standings[place] = {
            "mean": float(values.mean()),
            "sd": spread,
            "median_sem": float(np.median(list(noise.values()))),
            "countries": {iso3: {"mean": value, "sem": noise[iso3],
                                 "z": float((value - values.mean()) / spread) if spread > 0 else 0.0}
                          for iso3, value in means.items()},
        }
    return standings


def group_comparison(index: dict[str, float], labels: dict[str, str], permutations: int) -> dict:
    """Each group against every other country: the gap, its effect size, and a permutation p-value."""
    groups = {}
    for name in sorted(set(labels.values())):
        inside = np.array([v for iso3, v in index.items() if labels.get(iso3) == name])
        outside = np.array([v for iso3, v in index.items() if iso3 in labels and labels[iso3] != name])
        if inside.size == 0:
            continue
        groups[name] = {
            "countries": int(inside.size),
            "mean_index": float(inside.mean()),
            "d": cohens_d(inside, outside),
            "p": permutation_p(inside, outside, permutations),
        }
    return groups


def build_report(cfg: dict, out: Path, metric: str, permutations: int | None = None) -> dict:
    """Rank countries on one metric and test whether the ranking tracks region or income."""
    permutations = cfg["report"]["permutations"] if permutations is None else permutations
    summaries = load_summaries(out)
    standings = place_standings(summaries, metric)
    if not standings:
        raise SystemExit(f"Not enough countries measured to compare {metric!r}: at least three per place.")

    countries = {c["iso_a3"]: c for c in load_json(cfg["prompts"]["countries_file"])}
    income = json.loads((ROOT / cfg["report"]["income_file"]).read_text())

    index, detail = {}, {}
    for iso3 in sorted({iso3 for place in standings.values() for iso3 in place["countries"]}):
        places = {name: place["countries"][iso3] for name, place in standings.items()
                  if iso3 in place["countries"]}
        index[iso3] = float(np.mean([p["z"] for p in places.values()]))
        detail[iso3] = {
            "name": countries.get(iso3, {}).get("name", iso3),
            "region": countries.get(iso3, {}).get("region"),
            "subregion": countries.get(iso3, {}).get("subregion"),
            "income": income["labels"].get(income["countries"].get(iso3), None),
            "index": index[iso3],
            "places": places,
        }

    groupings = {
        "income": {iso3: d["income"] for iso3, d in detail.items() if d["income"]},
        "region": {iso3: d["region"] for iso3, d in detail.items() if d["region"]},
    }
    return {
        "run": out.name,
        "metric": metric,
        "metric_label": LABELS.get(metric, metric),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "places": {name: {k: v for k, v in place.items() if k != "countries"}
                   for name, place in standings.items()},
        "countries": detail,
        "groups": {name: group_comparison(index, labels, permutations)
                   for name, labels in groupings.items()},
    }


def print_report(report: dict, top: int | None = None) -> None:
    places = list(report["places"])
    ranked = sorted(report["countries"].items(), key=lambda kv: kv[1]["index"], reverse=True)
    shown = ranked if not top else ranked[:top] + ranked[-top:]

    print(f"\nRun {report['run']} · {report['metric']}: {report['metric_label']}")
    print(f"{len(report['countries'])} countries × {len(places)} places\n")
    header = f"{'':>4}  {'country':<22} {'index':>7}  " + "".join(f"{p:>9}" for p in places)
    print(header + f"  {'income':<20}")
    print("-" * len(header + "  " + " " * 20))
    for rank, (iso3, detail) in enumerate(shown, start=1):
        row = f"{rank:>4}  {detail['name'][:22]:<22} {detail['index']:>+7.2f}  "
        row += "".join(f"{detail['places'][p]['z']:>+9.2f}" if p in detail["places"] else f"{'-':>9}"
                       for p in places)
        print(row + f"  {(detail['income'] or '-'):<20}")

    print("\nHow much of this is noise?")
    for name, place in report["places"].items():
        print(f"  {name:<10} countries differ by sd {place['sd']:.3f}; "
              f"a single country's mean is measured to ±{place['median_sem']:.3f}")

    for grouping, groups in report["groups"].items():
        print(f"\nBy {grouping}:")
        for name, stats in sorted(groups.items(), key=lambda kv: kv[1]["mean_index"], reverse=True):
            d = f"d={stats['d']:+.2f}" if stats["d"] is not None else "d=n/a"
            p = f"p={stats['p']:.3f}" if stats["p"] is not None else "p=n/a"
            print(f"  {name:<22} {stats['countries']:>3} countries   "
                  f"index {stats['mean_index']:>+6.2f}   {d:<9} {p}")
    comparisons = sum(len(groups) for groups in report["groups"].values())
    print(f"\n{comparisons} group comparisons were made. One p-value below 0.05 among that many is "
          "what chance\nlooks like, so read the effect sizes and the noise line above before believing any "
          "of them.")
    print("\nIndex is the average z-score across places: how far this country sits from the average\n"
          "country, in country-to-country standard deviations. Positive means more of the metric.")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Compare how the model grades one country against another.")
    ap.add_argument("--metric", help="which measurement to rank by (default: report.metric)")
    ap.add_argument("--run", help="output folder under outputs/ (default: generation.run_name)")
    ap.add_argument("--top", type=int, help="show only the top and bottom N countries")
    args = ap.parse_args(argv)

    cfg = load_config()
    out = run_dir(cfg, args.run)
    report = build_report(cfg, out, args.metric or cfg["report"]["metric"])
    print_report(report, args.top)

    path = out / "analysis" / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"\nWritten to {path}")


if __name__ == "__main__":
    main()
