"""Sizing a run from its own noise: the arithmetic, and the two corrections that push n up."""
import json

import pytest

from blurred_lens.config import load_config
from blurred_lens.sizing import attenuation, images_for, shrink_factor, size_run

CFG = load_config()


def write_measured(root, run, per_country, places=("city",), metric="cast_b"):
    """A measured run: {iso3: (mean, sem, n)} for each place."""
    for iso3, (mean, sem, n) in per_country.items():
        for place in places:
            path = root / run / "analysis" / iso3 / f"{place}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "country": iso3, "place": place, "n_images": n, "excluded": {},
                "summary": {metric: {"mean": mean, "std": sem * n ** 0.5, "sem": sem, "n": n}},
                "images": []}))
    index = root / run / "analysis" / "index.json"
    index.write_text(json.dumps({f"{iso3}/{place}": {} for iso3 in per_country for place in places}))


def test_noise_dilutes_an_effect_by_a_known_amount():
    assert attenuation(spread=1.0, sem=0.0) == 1.0          # no noise, nothing lost
    assert attenuation(spread=1.0, sem=1.0) == pytest.approx(0.7071, abs=1e-4)
    assert attenuation(spread=0.0, sem=1.0) == 0.0          # no signal to survive


def test_the_sample_size_asked_for_delivers_the_target_it_was_asked_for():
    """Round-trip: size for a target, then check the noise at that size really hits it."""
    spread, sem_now, n_now = 1.5, 0.6, 50
    for target in (0.80, 0.90, 0.95, 0.99):
        n = images_for(spread, sem_now, n_now, target)
        sem_then = sem_now * (n_now / n) ** 0.5
        assert attenuation(spread, sem_then) >= target
        # and one image fewer would miss it, so the answer is not needlessly large
        if n > 1:
            looser = sem_now * (n_now / (n - 1)) ** 0.5
            assert attenuation(spread, looser) < target + 1e-6


def test_more_images_are_needed_for_a_stricter_target_and_a_fainter_signal():
    assert images_for(1.0, 0.5, 50, 0.95) > images_for(1.0, 0.5, 50, 0.80)
    assert images_for(0.5, 0.5, 50, 0.90) > images_for(2.0, 0.5, 50, 0.90)
    assert images_for(0.0, 0.5, 50, 0.9) is None  # no signal: no answer, rather than a wrong one


def test_a_pilot_picked_for_contrast_is_discounted_but_the_full_scope_is_not():
    """The pilot's spread overstates the full set's, so reading n off it undersizes the run."""
    scope = CFG["prompts"]["countries"]
    extremes = {"NOR", "SGP", "ARE", "ETH"}      # 60 degrees of latitude between them

    narrow, here, full = shrink_factor(extremes, CFG)
    whole, _, _ = shrink_factor(set(scope), CFG)

    assert (here, full) == (len(extremes), len(scope))
    assert narrow < 1.0
    assert whole == 1.0  # measuring everything is not a sample of itself


def test_the_spread_is_corrected_for_the_noise_inside_it(tmp_path):
    """What a pilot prints as the spread between countries already has its own noise baked in."""
    cfg = {**CFG, "paths": {**CFG["paths"], "outputs_dir": str(tmp_path)}}
    write_measured(tmp_path, "pilot", {
        "NOR": (-1.0, 0.5, 50), "NGA": (1.0, 0.5, 50), "SGP": (0.5, 0.5, 50), "ETH": (0.2, 0.5, 50)})

    sized = size_run(cfg, "pilot", "cast_b", target=0.95, group_size=12)
    city = sized["places"]["city"]

    assert city["true_sd"] < city["observed_sd"]
    assert city["discounted_sd"] == pytest.approx(city["true_sd"] * sized["shrink"])
    assert city["n"] == 50 and city["countries"] == 4
    assert 0 < city["attenuation_now"] < 1


def test_a_baseline_run_is_not_counted_as_a_country(tmp_path):
    """The no-country prompt is the zero, not one of the things being compared."""
    from blurred_lens.prompts import NO_COUNTRY
    cfg = {**CFG, "paths": {**CFG["paths"], "outputs_dir": str(tmp_path)}}
    write_measured(tmp_path, "pilot", {
        "NOR": (-1.0, 0.5, 50), "NGA": (1.0, 0.5, 50), "SGP": (0.5, 0.5, 50),
        NO_COUNTRY: (-9.0, 0.5, 50)})

    sized = size_run(cfg, "pilot", "cast_b", target=0.95, group_size=12)

    assert sized["places"]["city"]["countries"] == 3  # not 4


def test_too_few_countries_to_size_against(tmp_path):
    cfg = {**CFG, "paths": {**CFG["paths"], "outputs_dir": str(tmp_path)}}
    write_measured(tmp_path, "pilot", {"NOR": (-1.0, 0.5, 50), "NGA": (1.0, 0.5, 50)})

    assert size_run(cfg, "pilot", "cast_b", target=0.95, group_size=12)["places"] == {}


def test_averaging_places_is_what_the_budget_should_be_sized_against(tmp_path):
    """`report` ranks by an index over places, so one place alone overstates what is needed."""
    cfg = {**CFG, "paths": {**CFG["paths"], "outputs_dir": str(tmp_path)}}
    # Four countries whose grade is the same in every place, measured with the same noise.
    per_country = {"NOR": (-1.0, 0.4, 50), "NGA": (1.0, 0.4, 50),
                   "SGP": (0.6, 0.4, 50), "ETH": (0.1, 0.4, 50)}
    write_measured(tmp_path, "three", per_country, places=("city", "house", "village"))
    write_measured(tmp_path, "one", per_country, places=("city",))

    three = size_run(cfg, "three", "cast_b", target=0.95, group_size=12)
    one = size_run(cfg, "one", "cast_b", target=0.95, group_size=12)

    # Three places cut the noise on the index by about sqrt(3) against a single place...
    assert three["index"]["index_noise"] == pytest.approx(
        one["index"]["index_noise"] / 3 ** 0.5, rel=0.05)
    # ...so they ask for about a third of the images, and far fewer than any one place alone.
    assert three["index"]["images_needed"] < one["index"]["images_needed"]
    assert three["index"]["images_needed"] < min(
        p["images_needed"] for p in three["places"].values())


def test_the_index_needs_three_countries_measured_in_common(tmp_path):
    cfg = {**CFG, "paths": {**CFG["paths"], "outputs_dir": str(tmp_path)}}
    write_measured(tmp_path, "thin", {"NOR": (-1.0, 0.4, 50), "NGA": (1.0, 0.4, 50)})

    assert size_run(cfg, "thin", "cast_b", target=0.95, group_size=12)["index"] is None
