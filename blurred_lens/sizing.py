"""How many images per prompt does the comparison actually need?

    python -m blurred_lens.sizing --run phase2-free
    python -m blurred_lens.sizing --run phase2-noon --target 0.95 --metric cast_kelvin

Reads what a pilot measured and answers one question: how far does measurement noise dilute the
thing the project is trying to see, and what sample size would stop it mattering.

The quantity to protect is not a country's own mean but the *contrast* between groups of countries.
Noise on each country's mean adds to the real spread between countries, so an effect measured
through it is attenuated by

    sd_true / sqrt(sd_true^2 + sem^2)

which is what this prints. Sizing instead for "tell any two countries apart" asks for a far larger
sample than the group question needs, so it is the wrong target to spend a budget against.

Two corrections, both of which push the answer up rather than down:

1. **The observed spread between countries is inflated by the noise itself** -- what a pilot prints
   is sd_obs^2 = sd_true^2 + sem^2 -- so sizing against sd_obs flatters the sample. The true spread
   is recovered first.
2. **A pilot chosen for contrast overstates the spread** the full set will show. When a run covers
   fewer countries than prompts.countries asks for, the spread is discounted by the ratio of
   sd(|latitude|) over the full scope to sd(|latitude|) over the measured countries -- the one
   variable measurable for both, and the rival explanation for warmth. A run covering the whole
   scope is not discounted at all.
"""

import argparse
import json
import statistics as st

import numpy as np

from .config import load_config, run_dir
from .prompts import NO_COUNTRY, load_json
from .report import load_summaries


def attenuation(spread: float, sem: float) -> float:
    """The share of a real effect that survives measurement noise, between 0 and 1."""
    if spread <= 0:
        return 0.0
    return float(spread / np.hypot(spread, sem))


def images_for(spread: float, sem_now: float, n_now: int, target: float) -> int | None:
    """Images per prompt at which `target` of a real effect would survive the noise."""
    if spread <= 0 or sem_now <= 0 or not 0 < target < 1:
        return None
    needed = (sem_now ** 2 * n_now * target ** 2) / (spread ** 2 * (1 - target ** 2))
    return max(1, int(needed + 0.999))


def shrink_factor(measured: set[str], cfg: dict) -> tuple[float, int, int]:
    """How much narrower the full country scope is than the countries actually measured.

    A pilot picked for contrast (Norway and Singapore against Ethiopia and Afghanistan) spreads
    wider than the set it stands in for, so its spread has to be discounted before any sample size
    is read off it. Absolute latitude is the yardstick: it is known for every country, and it is the
    rival explanation the whole design is built to separate from income.
    """
    scope = cfg["prompts"].get("countries") or []
    latitude = {c["iso_a3"]: abs(c["latitude"])
                for c in load_json(cfg["prompts"]["countries_file"]) if c.get("latitude") is not None}
    full = [latitude[i] for i in scope if i in latitude] or list(latitude.values())
    here = [latitude[i] for i in measured if i in latitude]
    if len(here) < 2 or len(full) < 2:
        return 1.0, len(here), len(full)
    spread_here, spread_full = st.stdev(here), st.stdev(full)
    if spread_here == 0:
        return 1.0, len(here), len(full)
    return min(1.0, spread_full / spread_here), len(here), len(full)


def size_run(cfg: dict, run: str, metric: str, target: float, group_size: int) -> dict:
    """Per place: the spread, the noise, what survives it now, and what sample size would fix it."""
    summaries = load_summaries(run_dir(cfg, run))
    measured = {iso3 for iso3, _ in summaries if iso3 != NO_COUNTRY}
    factor, here, full = shrink_factor(measured, cfg)
    places = {}
    for place in sorted({p for _, p in summaries}):
        rows = [data["summary"][metric] for (iso3, p), data in summaries.items()
                if p == place and iso3 != NO_COUNTRY and metric in data.get("summary", {})]
        if len(rows) < 3:
            continue
        n_now = int(st.median([r["n"] for r in rows]))
        sem = float(st.median([r["sem"] for r in rows]))
        observed = float(st.stdev([r["mean"] for r in rows]))
        true = float(max(observed ** 2 - sem ** 2, 0.0) ** 0.5)
        places[place] = {
            "countries": len(rows), "n": n_now, "sem": sem,
            "observed_sd": observed, "true_sd": true, "discounted_sd": true * factor,
            "attenuation_now": attenuation(true * factor, sem),
            "images_needed": images_for(true * factor, sem, n_now, target),
            # With `group_size` countries in a group, noise on the group's mean shrinks by its root.
            "group_mean_error_sd": (sem / group_size ** 0.5 / (true * factor))
                                   if true * factor > 0 else None,
        }
    return {"run": run, "metric": metric, "target": target, "shrink": factor,
            "countries_measured": here, "countries_in_scope": full, "places": places}


def print_sizing(sized: dict) -> None:
    print(f"\nRun {sized['run']} · {sized['metric']}")
    if sized["shrink"] < 1:
        print(f"  {sized['countries_measured']} of {sized['countries_in_scope']} countries measured, "
              f"and more spread out than the full scope: discounting the spread between countries "
              f"by ×{sized['shrink']:.2f}.")
    print(f"  Target: {sized['target'] * 100:.0f}% of a real effect surviving the noise.\n")
    if not sized["places"]:
        print("  Nothing measured yet for this metric: at least three countries in one place.")
        return
    print(f"  {'place':<10} {'n':>5} {'±1 country':>11} {'spread':>8} {'survives':>9} {'need n':>8}")
    print("  " + "-" * 55)
    for place, row in sized["places"].items():
        need = row["images_needed"]
        print(f"  {place:<10} {row['n']:>5} {row['sem']:>11.3f} {row['discounted_sd']:>8.3f} "
              f"{row['attenuation_now'] * 100:>8.0f}% {('-' if need is None else need):>8}")
    worst = max((r["images_needed"] or 0) for r in sized["places"].values())
    print(f"\n  -> {worst} images per prompt, set by the place that needs most.")
    print("     'survives' is sd_true/sqrt(sd_true^2+sem^2): the share of a real group difference\n"
          "     left after measurement noise dilutes it. 'spread' is already noise-corrected and\n"
          "     discounted. Sizing to tell two individual countries apart would ask for far more.")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Pick images per prompt from a pilot's measured noise.")
    ap.add_argument("--run", help="output folder under outputs/ (default: generation.run_name)")
    ap.add_argument("--metric", help="which measurement to size for (default: report.metric)")
    ap.add_argument("--target", type=float, default=0.95,
                    help="share of a real effect that must survive the noise (default: 0.95)")
    ap.add_argument("--group-size", type=int, default=12,
                    help="countries per group in the comparison being powered (default: 12)")
    ap.add_argument("--json", action="store_true", help="print the numbers as JSON instead")
    args = ap.parse_args(argv)

    cfg = load_config()
    sized = size_run(cfg, args.run or cfg["generation"]["run_name"],
                     args.metric or cfg["report"]["metric"], args.target, args.group_size)
    print(json.dumps(sized, indent=1)) if args.json else print_sizing(sized)


if __name__ == "__main__":
    main()
