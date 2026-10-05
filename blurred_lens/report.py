"""Compare countries: does the model grade some of them warmer, dustier or darker than others?

    python -m blurred_lens.report                            # the headline metric from config.toml
    python -m blurred_lens.report --metric haze              # rank by something else
    python -m blurred_lens.report --run phase2-noon
    python -m blurred_lens.report --run phase2-noon --baseline phase2-baseline-noon

Reads what blurred_lens.analyze measured and answers one question at a time: for the same kind of
place, how far from the middle does each country sit, and do those distances line up with region or
income rather than with geography?

Two rules keep the comparison honest. Countries are compared within a place -- a city against other
countries' cities, never against farms -- because place types differ in color for reasons that have
nothing to do with the country. And the country, not the image, is the unit of comparison: 500
images of one prompt say precisely what that one answer looks like, not that the answer is common,
so the group tests below shuffle country labels rather than image labels.

Two yardsticks, not one. A country's z-score says how far it sits from the average country, which
says who is warmest but not whether the model is doing anything unusual to anyone. Pass --baseline a
run generated with a no-country prompt and every country is also reported as a deviation from the
model's own default picture of the same place -- a zero that does not move when the set of countries
changes.

And the ranking has to survive latitude. Near the equator the light really is harsher and warmer, so
a warmth ranking that tracks income might only be tracking distance from the equator; the two are
badly confounded across the world's countries. Every group test is therefore run twice: once on the
ranking, once on what is left of it after a straight line in |latitude| has been taken out.

What this can and cannot show: with the prompt, the camera view, the model and the size all fixed,
the country name is the only thing that changes between two prompts for the same place. A gap here
is therefore caused by the country name. Whether the model is wrong to draw Lagos warmer than Oslo
is a separate question this cannot answer -- but a gap that tracks income and survives latitude is
the shape of the claim the media-studies literature makes about the yellow filter.
"""

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .analyze import analysis_path
from .config import ROOT, load_config, run_dir
from .prompts import NO_COUNTRY, load_json

# The covariates a run can hold constant, from data/countries.json. Each is transformed to the
# quantity that actually matters: distance from the equator rather than signed latitude, and rainfall
# on a log scale, because the difference between 100mm and 200mm of rain changes how a place looks
# far more than the difference between 2,000mm and 2,100mm.
CONTROLS = {
    "latitude": ("|latitude|", abs),
    "aridity_index": ("log10 aridity", lambda v: math.log10(max(float(v), 0.1))),
    "precipitation_mm": ("log10 rainfall", lambda v: math.log10(max(float(v), 1.0))),
    "temperature_c": ("mean temperature", float),
    "forest_pct": ("forest cover %", float),
    "population": ("log10 population", lambda v: math.log10(max(float(v), 1.0))),
}

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


def load_baseline(out: Path, metric: str) -> dict[str, dict[str, float]]:
    """The no-country prompt's measurements for each place, from a baseline run folder.

    A baseline run names no country, so its images sit under NO_COUNTRY rather than an ISO code and
    it has one prompt per place. Those numbers are the model's own default picture of a city, a
    village, a house -- the zero a country's warmth can be measured from, instead of measuring every
    country only against the average country.
    """
    folder = out / "analysis" / NO_COUNTRY
    if not folder.is_dir():
        raise SystemExit(
            f"No no-country baseline in {folder}. Generate one with "
            f"`python -m blurred_lens.generate --condition baseline` and measure it, or drop "
            f"--baseline.")
    found = {}
    for path in sorted(folder.glob("*.json")):
        summary = json.loads(path.read_text()).get("summary", {})
        if metric in summary:
            found[path.stem] = {"mean": summary[metric]["mean"], "sem": summary[metric]["sem"],
                                "n": summary[metric]["n"]}
    return found


def least_squares(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    """Coefficients of y on `x` (with an intercept column), and the share of y's variance explained."""
    design = np.column_stack([np.ones(len(y)), x])
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    total = float(((y - y.mean()) ** 2).sum())
    residual = float(((y - design @ beta) ** 2).sum())
    return beta, (0.0 if total == 0 else 1 - residual / total)


def residuals_after(values: dict[str, float],
                    covariates: dict[str, dict[str, float]]) -> tuple[dict[str, float], dict | None]:
    """Every country's value with a straight-line fit on every covariate taken out of it.

    This is what the covariates in data/countries.json are for. Near the equator the light really is
    harsher and warmer, and a dry country really does look dustier, so a warmth ranking that tracks
    income might only be tracking distance from the equator or how much it rains. Fitting those and
    keeping the residuals asks the income question again of what they leave unexplained, and `alone`
    in the fit says how much each one accounts for by itself, so it is visible which rival
    explanation is doing the work.

    These are straight lines, not a climate model. They cannot separate a stereotype from a climate,
    only say whether the pattern needs more than climate to describe it.

    Returns the values unchanged, and no fit, when there is nothing to fit: too few countries
    carrying every covariate, or a covariate that never varies among them.
    """
    names = sorted(covariates)
    shared = sorted(set(values).intersection(*(set(covariates[n]) for n in names))) if names else []
    if len(shared) < len(names) + 2:
        return dict(values), None
    x = np.array([[covariates[n][iso3] for n in names] for iso3 in shared], dtype=np.float64)
    y = np.array([values[iso3] for iso3 in shared], dtype=np.float64)
    if any(x[:, i].std() == 0 for i in range(x.shape[1])):
        return dict(values), None
    beta, explained = least_squares(x, y)
    predicted = np.column_stack([np.ones(len(y)), x]) @ beta
    return (
        {iso3: float(y[i] - predicted[i]) for i, iso3 in enumerate(shared)},
        {
            "countries": len(shared),
            "r2": explained,
            "intercept": float(beta[0]),
            "terms": {n: float(beta[i + 1]) for i, n in enumerate(names)},
            # What each covariate accounts for on its own, so the one doing the work is visible.
            "alone": {n: least_squares(x[:, [i]], y)[1] for i, n in enumerate(names)},
        },
    )


def place_standings(summaries: dict, metric: str, baseline: dict | None = None) -> dict[str, dict]:
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
        default = (baseline or {}).get(place)
        countries = {}
        for iso3, value in means.items():
            row = {"mean": value, "sem": noise[iso3],
                   "z": float((value - values.mean()) / spread) if spread > 0 else 0.0}
            if default:
                # How far this country sits from the model's own default picture of this place, in
                # the metric's units and again as a share of how much countries differ at all.
                row["delta"] = float(value - default["mean"])
                row["delta_sem"] = float(np.hypot(noise[iso3], default["sem"]))
                row["delta_z"] = float(row["delta"] / spread) if spread > 0 else 0.0
            countries[iso3] = row
        standings[place] = {
            "mean": float(values.mean()),
            "sd": spread,
            "median_sem": float(np.median(list(noise.values()))),
            "baseline": default,
            "countries": countries,
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


def build_report(cfg: dict, out: Path, metric: str, permutations: int | None = None,
                 baseline_dir: Path | None = None) -> dict:
    """Rank countries on one metric and test whether the ranking tracks region or income.

    With `baseline_dir`, every country is also reported as a deviation from the no-country prompt
    measured in that run -- the model's own default for the same place. And because latitude is the
    rival explanation for warmth, each group test is run twice: on the ranking, and on what is left
    of it once a straight line in distance from the equator has been taken out.
    """
    permutations = cfg["report"]["permutations"] if permutations is None else permutations
    summaries = load_summaries(out)
    baseline = load_baseline(baseline_dir, metric) if baseline_dir else None
    standings = place_standings(summaries, metric, baseline)
    if not standings:
        raise SystemExit(f"Not enough countries measured to compare {metric!r}: at least three per place.")

    countries = {c["iso_a3"]: c for c in load_json(cfg["prompts"]["countries_file"])}
    income = json.loads((ROOT / cfg["report"]["income_file"]).read_text())

    index, baseline_index, detail = {}, {}, {}
    for iso3 in sorted({iso3 for place in standings.values() for iso3 in place["countries"]}):
        places = {name: place["countries"][iso3] for name, place in standings.items()
                  if iso3 in place["countries"]}
        index[iso3] = float(np.mean([p["z"] for p in places.values()]))
        deltas = [p["delta_z"] for p in places.values() if "delta_z" in p]
        detail[iso3] = {
            "name": countries.get(iso3, {}).get("name", iso3),
            "region": countries.get(iso3, {}).get("region"),
            "subregion": countries.get(iso3, {}).get("subregion"),
            "latitude": countries.get(iso3, {}).get("latitude"),
            "precipitation_mm": countries.get(iso3, {}).get("precipitation_mm"),
            "aridity_index": countries.get(iso3, {}).get("aridity_index"),
            "forest_pct": countries.get(iso3, {}).get("forest_pct"),
            "income": income["labels"].get(income["countries"].get(iso3), None),
            "index": index[iso3],
            "places": places,
        }
        if deltas:
            baseline_index[iso3] = float(np.mean(deltas))
            detail[iso3]["baseline_index"] = baseline_index[iso3]

    # The rival explanations this ranking has to survive: climate, and anything else recorded.
    covariates = {}
    for name in (cfg["report"].get("controls") or []):
        if name not in CONTROLS:
            raise SystemExit(f"report.controls: unknown control {name!r}; "
                             f"choose from {', '.join(CONTROLS)}")
        transform = CONTROLS[name][1]
        values = {iso3: transform(countries[iso3][name]) for iso3 in detail
                  if countries.get(iso3, {}).get(name) is not None}
        if values:
            covariates[name] = values
    net, fit = residuals_after(index, covariates)
    for iso3, value in net.items():
        detail[iso3]["index_net_of_controls"] = value

    groupings = {
        "income": {iso3: d["income"] for iso3, d in detail.items() if d["income"]},
        "region": {iso3: d["region"] for iso3, d in detail.items() if d["region"]},
    }
    return {
        "run": out.name,
        "metric": metric,
        "metric_label": LABELS.get(metric, metric),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "baseline_run": baseline_dir.name if baseline_dir else None,
        "places": {name: {k: v for k, v in place.items() if k != "countries"}
                   for name, place in standings.items()},
        "countries": detail,
        "controls": ({**fit, "labels": {n: CONTROLS[n][0] for n in covariates}} if fit else None),
        "groups": {name: group_comparison(index, labels, permutations)
                   for name, labels in groupings.items()},
        "groups_net_of_controls": {name: group_comparison(net, labels, permutations)
                                   for name, labels in groupings.items()} if fit else {},
    }


def print_report(report: dict, top: int | None = None) -> None:
    places = list(report["places"])
    ranked = sorted(report["countries"].items(), key=lambda kv: kv[1]["index"], reverse=True)
    shown = ranked if not top else ranked[:top] + ranked[-top:]

    versus = report.get("baseline_run")
    print(f"\nRun {report['run']} · {report['metric']}: {report['metric_label']}")
    print(f"{len(report['countries'])} countries × {len(places)} places"
          + (f" · against the no-country baseline in {versus}" if versus else "") + "\n")
    extra = f"{'vs base':>9}" if versus else ""
    header = (f"{'':>4}  {'country':<22} {'index':>7}{extra}  " + "".join(f"{p:>9}" for p in places))
    print(header + f"  {'|lat|':>6} {'rain':>6}  {'income':<20}")
    print("-" * len(header + "  " + " " * 35))
    for rank, (iso3, detail) in enumerate(shown, start=1):
        row = f"{rank:>4}  {detail['name'][:22]:<22} {detail['index']:>+7.2f}"
        if versus:
            row += f"{detail['baseline_index']:>+9.2f}" if "baseline_index" in detail else f"{'-':>9}"
        row += "  " + "".join(f"{detail['places'][p]['z']:>+9.2f}" if p in detail["places"]
                              else f"{'-':>9}" for p in places)
        lat = f"{abs(detail['latitude']):>6.0f}" if detail.get("latitude") is not None else f"{'-':>6}"
        rain = f"{detail['precipitation_mm']:>6,}" if detail.get("precipitation_mm") else f"{'-':>6}"
        print(row + f"  {lat} {rain}  {(detail['income'] or '-'):<20}")

    print("\nHow much of this is noise?")
    for name, place in report["places"].items():
        line = (f"  {name:<10} countries differ by sd {place['sd']:.3f}; "
                f"a single country's mean is measured to ±{place['median_sem']:.3f}")
        if place.get("baseline"):
            line += (f"; the model's own default is {place['baseline']['mean']:+.3f}"
                     f"±{place['baseline']['sem']:.3f}")
        print(line)

    def print_groups(groups: dict, label: str) -> None:
        print(f"\nBy {label}:")
        for name, stats in sorted(groups.items(), key=lambda kv: kv[1]["mean_index"], reverse=True):
            d = f"d={stats['d']:+.2f}" if stats["d"] is not None else "d=n/a"
            p = f"p={stats['p']:.3f}" if stats["p"] is not None else "p=n/a"
            print(f"  {name:<22} {stats['countries']:>3} countries   "
                  f"index {stats['mean_index']:>+6.2f}   {d:<9} {p}")

    for grouping, groups in report["groups"].items():
        print_groups(groups, grouping)

    fit = report.get("controls")
    if fit:
        held = ", ".join(fit["labels"].values())
        width = max(len(label) for label in fit["labels"].values())
        print(f"\nRival explanations ({fit['countries']} countries):")
        for name, label in fit["labels"].items():
            print(f"  {label:<{width}}  alone accounts for {fit['alone'][name] * 100:>3.0f}% of the "
                  f"spread between countries  (slope {fit['terms'][name]:+.3f})")
        if len(fit["labels"]) > 1:
            print(f"  {'together':<{width}}  {'':18}{fit['r2'] * 100:>3.0f}%")
        for grouping, groups in report.get("groups_net_of_controls", {}).items():
            print_groups(groups, f"{grouping}, with {held} held constant")
        print(f"  A group that keeps its gap here needs more than {held} to explain it. One that\n"
              f"  loses it was tracking climate all along. These are straight lines, not a climate\n"
              f"  model: they cannot tell a stereotype from a climate, only whether the pattern\n"
              f"  survives the most obvious confounds.")

    comparisons = sum(len(groups) for groups in report["groups"].values())
    comparisons += sum(len(groups) for groups in report.get("groups_net_of_controls", {}).values())
    print(f"\n{comparisons} group comparisons were made. One p-value below 0.05 among that many is "
          "what chance\nlooks like, so read the effect sizes and the noise line above before believing any "
          "of them.")
    print("\nIndex is the average z-score across places: how far this country sits from the average\n"
          "country, in country-to-country standard deviations. Positive means more of the metric.")
    if versus:
        print("'vs base' is the same distance measured from the model's own picture of the place with\n"
              "no country named at all, rather than from the average country.")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Compare how the model grades one country against another.")
    ap.add_argument("--metric", help="which measurement to rank by (default: report.metric)")
    ap.add_argument("--run", help="output folder under outputs/ (default: generation.run_name)")
    ap.add_argument("--top", type=int, help="show only the top and bottom N countries")
    ap.add_argument("--baseline", help="run folder holding the no-country baseline, so each country "
                                       "is also reported as a deviation from the model's own default "
                                       "(default: report.baseline_run)")
    args = ap.parse_args(argv)

    cfg = load_config()
    out = run_dir(cfg, args.run)
    wanted = args.baseline if args.baseline is not None else cfg["report"].get("baseline_run")
    baseline_dir = run_dir(cfg, wanted) if wanted else None
    report = build_report(cfg, out, args.metric or cfg["report"]["metric"], baseline_dir=baseline_dir)
    print_report(report, args.top)

    path = out / "analysis" / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"\nWritten to {path}")


if __name__ == "__main__":
    main()
