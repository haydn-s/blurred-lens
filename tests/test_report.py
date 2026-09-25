"""End to end: plant a known grade on one country and check the comparison finds it."""
import cv2
import numpy as np
import pytest
from PIL import Image

from blurred_lens import analyze, report
from blurred_lens.config import load_config

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
