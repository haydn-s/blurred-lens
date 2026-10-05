"""End to end: plant a known grade on one country and check the comparison finds it."""
import json

import cv2
import numpy as np
import pytest
from PIL import Image

from blurred_lens import analyze, report
from blurred_lens.config import load_config
from blurred_lens.prompts import NO_COUNTRY

COUNTRIES = ["USA", "NOR", "JPN", "NGA", "IND"]
WARMED = "NGA"
PLACES = ["city", "village"]


def photo(seed, gains=(1.0, 1.0, 1.0)):
    rng = np.random.default_rng(seed)
    small = rng.integers(50, 210, (8, 8, 3), dtype=np.uint8)
    image = cv2.resize(small, (64, 64), interpolation=cv2.INTER_LINEAR)
    return np.clip(image * np.array(gains), 0, 255).astype(np.uint8)


@pytest.fixture
def measured(tmp_path, monkeypatch):
    """A run where every country gets the same pictures, except one that is graded warm."""
    cfg = load_config()
    cfg["paths"]["outputs_dir"] = str(tmp_path)
    cfg["generation"]["run_name"] = "test"
    cfg["generation"]["images_per_prompt"] = 3
    cfg["analysis"]["width"] = 64
    monkeypatch.setattr(analyze, "load_config", lambda: cfg)

    for iso3 in COUNTRIES:
        gains = (1.18, 1.02, 0.78) if iso3 == WARMED else (1.0, 1.0, 1.0)
        for place in PLACES:
            folder = tmp_path / "test" / "images" / iso3 / place
            folder.mkdir(parents=True)
            for i in range(1, 4):
                Image.fromarray(photo(seed=i, gains=gains)).save(folder / f"{i:04d}.png")
    analyze.main([])
    return cfg, tmp_path / "test"


def test_the_graded_country_tops_the_ranking(measured):
    cfg, out = measured

    built = report.build_report(cfg, out, "cast_b", permutations=200)

    ranked = sorted(built["countries"], key=lambda iso3: built["countries"][iso3]["index"], reverse=True)
    assert ranked[0] == WARMED
    assert built["countries"][WARMED]["index"] > 1.5  # well clear of the other countries
    assert all(built["countries"][iso3]["index"] < 0.5 for iso3 in COUNTRIES if iso3 != WARMED)


def test_the_same_country_is_coolest_in_kelvin(measured):
    """A warm grade is fewer kelvin, so the sign flips when the metric does."""
    cfg, out = measured

    built = report.build_report(cfg, out, "cast_kelvin", permutations=200)

    coolest = min(built["countries"], key=lambda iso3: built["countries"][iso3]["index"])
    assert coolest == WARMED


def test_ungraded_countries_look_alike(measured):
    """Nothing but noise separates identical pictures: guards against inventing a finding."""
    cfg, out = measured

    built = report.build_report(cfg, out, "cast_b", permutations=200)

    plain = [built["countries"][iso3]["index"] for iso3 in COUNTRIES if iso3 != WARMED]
    assert max(plain) - min(plain) < 1.0


def test_the_report_carries_region_income_and_noise(measured):
    cfg, out = measured

    built = report.build_report(cfg, out, "cast_b", permutations=200)

    assert built["countries"]["NGA"]["income"] == "Lower middle income"
    assert built["countries"]["NOR"]["region"] == "Europe"
    assert set(built["places"]) == set(PLACES)
    assert built["places"]["city"]["median_sem"] >= 0
    assert set(built["groups"]) == {"income", "region"}


def test_group_comparison_reports_effect_size_and_p(measured):
    cfg, out = measured

    groups = report.build_report(cfg, out, "cast_b", permutations=200)["groups"]["income"]

    high = groups["High income"]
    assert high["countries"] == 3  # USA, NOR, JPN
    assert high["d"] is not None and high["p"] is not None
    assert 0 < high["p"] <= 1


# ---------------------------------------------------------------- the no-country baseline --------

def write_baseline(root, value, places=PLACES, sem=0.0):
    """A measured baseline run: one no-country prompt per place."""
    for place in places:
        path = root / "analysis" / NO_COUNTRY / f"{place}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "country": NO_COUNTRY, "place": place, "n_images": 10, "excluded": {},
            "summary": {"cast_b": {"mean": value, "std": 1.0, "sem": sem, "n": 10}}, "images": []}))
    return root


def test_each_country_is_also_measured_from_the_models_own_default(measured, tmp_path):
    """The z-score says who is warmest; the baseline says whether anyone is being warmed at all."""
    cfg, out = measured
    base = write_baseline(tmp_path / "baseline", value=-2.0)

    built = report.build_report(cfg, out, "cast_b", permutations=200, baseline_dir=base)

    assert built["baseline_run"] == "baseline"
    assert built["places"]["city"]["baseline"]["mean"] == -2.0
    entry = built["countries"][WARMED]["places"]["city"]
    assert entry["delta"] == pytest.approx(entry["mean"] + 2.0)
    # The graded country is the furthest from the default, as it is from the average country.
    deltas = {iso3: d["baseline_index"] for iso3, d in built["countries"].items()}
    assert max(deltas, key=deltas.get) == WARMED


def test_the_baseline_shifts_every_country_together_and_the_ranking_not_at_all(measured, tmp_path):
    """A different default moves all the deltas by the same amount: it is a zero, not a yardstick."""
    cfg, out = measured
    low = report.build_report(cfg, out, "cast_b", 200, write_baseline(tmp_path / "a", -2.0))
    high = report.build_report(cfg, out, "cast_b", 200, write_baseline(tmp_path / "b", +3.0))

    shifts = {iso3: low["countries"][iso3]["baseline_index"] - high["countries"][iso3]["baseline_index"]
              for iso3 in COUNTRIES}
    assert len(set(round(v, 6) for v in shifts.values())) == 1
    assert [low["countries"][i]["index"] for i in COUNTRIES] == \
           [high["countries"][i]["index"] for i in COUNTRIES]


def test_a_missing_baseline_says_so_rather_than_reporting_zeroes(measured, tmp_path):
    cfg, out = measured
    with pytest.raises(SystemExit, match="no-country baseline"):
        report.build_report(cfg, out, "cast_b", 200, baseline_dir=tmp_path / "not-generated")


# ------------------------------------------------------------------ the latitude control ---------

def test_a_covariate_is_taken_out_of_a_ranking_that_was_only_that_covariate():
    """Warmth that is exactly distance from the equator must leave nothing behind."""
    equator = {"A": 0.0, "B": 10.0, "C": 20.0, "D": 30.0, "E": 40.0}
    index = {iso3: 2.0 - 0.05 * lat for iso3, lat in equator.items()}

    net, fit = report.residuals_after(index, {"latitude": equator})

    assert fit["r2"] == pytest.approx(1.0)
    assert fit["terms"]["latitude"] == pytest.approx(-0.05)
    assert fit["alone"]["latitude"] == pytest.approx(1.0)
    assert all(abs(v) < 1e-9 for v in net.values())


def test_several_covariates_are_taken_out_together_and_scored_apart():
    """`alone` is what makes it visible which rival explanation is doing the work."""
    rain = {"A": 0.0, "B": 1.0, "C": 2.0, "D": 3.0, "E": 4.0}
    flat = {"A": 1.0, "B": 0.0, "C": 1.0, "D": 0.0, "E": 1.0}  # carries none of the signal
    index = {iso3: 3.0 - 0.5 * v for iso3, v in rain.items()}

    net, fit = report.residuals_after(index, {"rain": rain, "forest": flat})

    assert fit["alone"]["rain"] == pytest.approx(1.0)
    assert fit["alone"]["forest"] == pytest.approx(0.0, abs=0.05)
    assert fit["countries"] == 5
    assert all(abs(v) < 1e-9 for v in net.values())


def test_a_ranking_unrelated_to_the_covariate_survives_the_control():
    """The point of the control is to leave a real pattern standing, not to flatten everything."""
    equator = {"A": 0.0, "B": 10.0, "C": 20.0, "D": 30.0, "E": 40.0}
    index = {"A": 1.0, "B": -1.0, "C": 1.0, "D": -1.0, "E": 1.0}  # alternates, so no slope

    net, fit = report.residuals_after(index, {"latitude": equator})

    assert abs(fit["r2"]) < 0.2
    assert np.std(list(net.values())) > 0.8 * np.std(list(index.values()))


def test_an_income_gap_that_is_really_latitude_disappears_from_the_group_test():
    """The confound this project exists to rule out, end to end through the group comparison."""
    # Poor countries near the equator, rich ones far from it -- the world's actual arrangement.
    equator = {"P1": 2.0, "P2": 6.0, "P3": 10.0, "R1": 45.0, "R2": 52.0, "R3": 60.0}
    warmth = {iso3: -0.04 * lat for iso3, lat in equator.items()}  # warmth is latitude, nothing else
    labels = {"P1": "poor", "P2": "poor", "P3": "poor", "R1": "rich", "R2": "rich", "R3": "rich"}

    raw = report.group_comparison(warmth, labels, permutations=500)
    net, _ = report.residuals_after(warmth, {"latitude": equator})
    controlled = report.group_comparison(net, labels, permutations=500)

    assert raw["poor"]["mean_index"] > raw["rich"]["mean_index"]      # looks like an income effect
    assert abs(raw["poor"]["d"]) > 2                                  # and a huge one
    assert abs(controlled["poor"]["mean_index"]) < 1e-9               # until latitude is held constant
    assert controlled["poor"]["p"] == pytest.approx(1.0, abs=0.01)


def test_residuals_need_something_to_fit():
    values = {"A": 1.0, "B": 2.0, "C": 3.0}
    flat = {"A": 7.0, "B": 7.0, "C": 7.0}
    assert report.residuals_after(values, {"flat": flat}) == (values, None)   # never varies
    assert report.residuals_after(values, {}) == (values, None)               # nothing named
    # One country cannot support a fit with an intercept and a slope.
    assert report.residuals_after({"A": 1.0}, {"x": {"A": 5.0}}) == ({"A": 1.0}, None)


def test_the_report_runs_every_group_test_twice(measured):
    cfg, out = measured
    # Five countries cannot support the four controls config.toml asks for by default.
    cfg = {**cfg, "report": {**cfg["report"], "controls": ["latitude", "forest_pct"]}}

    built = report.build_report(cfg, out, "cast_b", permutations=200)

    assert built["controls"]["countries"] == len(COUNTRIES)
    assert set(built["controls"]["labels"]) == {"latitude", "forest_pct"}
    assert set(built["groups_net_of_controls"]) == {"income", "region"}
    for d in built["countries"].values():
        for field in ("latitude", "precipitation_mm", "aridity_index", "forest_pct"):
            assert d[field] is not None


def test_more_controls_than_countries_can_carry_are_refused(measured):
    """Fitting four covariates through five countries would explain anything; better to say nothing."""
    cfg, out = measured
    assert len(COUNTRIES) == 5
    cfg = {**cfg, "report": {**cfg["report"],
           "controls": ["latitude", "temperature_c", "precipitation_mm", "forest_pct"]}}

    built = report.build_report(cfg, out, "cast_b", permutations=200)

    assert built["controls"] is None
    assert built["groups_net_of_controls"] == {}
    assert built["groups"]           # the uncontrolled comparison is still reported


def test_an_unknown_control_is_refused_rather_than_ignored(measured):
    """Silently dropping a control would report an uncontrolled result as a controlled one."""
    cfg, out = measured
    cfg = {**cfg, "report": {**cfg["report"], "controls": ["altitude"]}}

    with pytest.raises(SystemExit, match="altitude"):
        report.build_report(cfg, out, "cast_b", permutations=200)


def test_rainfall_can_absorb_a_gap_that_latitude_cannot():
    """The phase-2 result in miniature: dry countries read warm, and latitude does not see it."""
    # Two groups matched on latitude but not on rainfall; warmth is rainfall and nothing else.
    equator = {"D1": 10.0, "D2": 30.0, "D3": 50.0, "W1": 10.0, "W2": 30.0, "W3": 50.0}
    rain = {"D1": 2.0, "D2": 2.1, "D3": 1.9, "W1": 3.3, "W2": 3.2, "W3": 3.4}
    warmth = {iso3: -2.0 * v for iso3, v in rain.items()}
    labels = {k: ("dry" if k.startswith("D") else "wet") for k in rain}

    by_latitude, lat_fit = report.residuals_after(warmth, {"latitude": equator})
    by_rain, rain_fit = report.residuals_after(warmth, {"rain": rain})

    assert lat_fit["r2"] < 0.05                                   # latitude explains nothing
    assert rain_fit["r2"] == pytest.approx(1.0)                   # rainfall explains all of it
    assert abs(report.group_comparison(by_latitude, labels, 500)["dry"]["d"]) > 2
    assert abs(report.group_comparison(by_rain, labels, 500)["dry"]["mean_index"]) < 1e-9
