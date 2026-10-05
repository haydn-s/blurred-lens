import json
from collections import Counter

import pytest

from blurred_lens.config import ROOT, load_config
from blurred_lens.prompts import (NO_COUNTRY, build_prompts, conditions, load_json, load_prompts,
                                  names_a_country, select)

CFG = load_config()
COUNTRIES = load_json(CFG["prompts"]["countries_file"])
PLACES = load_json(CFG["prompts"]["places_file"])


def test_countries_are_unique_and_complete():
    assert len({c["iso_a3"] for c in COUNTRIES}) == len(COUNTRIES)
    numeric = [c["iso_num"] for c in COUNTRIES if c["iso_num"]]
    assert len(set(numeric)) == len(numeric)  # the map matches shapes by numeric code
    for c in COUNTRIES:
        assert c["name"] and c["prompt_name"] and c["region"] and c["subregion"], c


def test_place_ids_are_unique():
    assert len({p["id"] for p in PLACES}) == len(PLACES)


def test_one_prompt_per_country_place_pair():
    countries, places = ["USA", "JPN"], ["city", "house"]
    assert len(load_prompts(CFG, countries, places)) == len(countries) * len(places)


def test_the_configured_scope_decides_what_a_run_covers():
    wanted_countries = CFG["prompts"].get("countries") or [c["iso_a3"] for c in COUNTRIES]
    wanted_places = CFG["prompts"].get("places") or [p["id"] for p in PLACES]

    prompts = load_prompts(CFG)

    assert {p.iso3 for p in prompts} == set(wanted_countries)
    assert {p.place for p in prompts} == set(wanted_places)
    assert len(prompts) == len(wanted_countries) * len(wanted_places)


def test_every_place_has_a_camera_view():
    assert all(p["view"].strip() for p in PLACES)


def test_prompt_text_fills_country_place_and_view():
    [prompt] = build_prompts(
        [{"iso_a3": "USA", "prompt_name": "the United States"}],
        [{"id": "city", "phrase": "a city", "view": "taken at eye level"}],
        "A photograph of {place} in {country}, {view}.",
    )
    assert prompt.text == "A photograph of a city in the United States, taken at eye level."


def test_select_rejects_unknown_ids():
    with pytest.raises(ValueError, match="ctiy"):
        select(PLACES, ["ctiy"], "id")


def test_every_country_has_a_latitude_to_control_for():
    """Latitude is the rival explanation for warmth, so every country carries one."""
    for c in COUNTRIES:
        assert isinstance(c["latitude"], (int, float)), c
        assert -90 <= c["latitude"] <= 90, c


def test_every_condition_fixes_the_place_and_the_camera():
    for name, template in conditions(CFG).items():
        assert "{place}" in template and "{view}" in template, name


def test_a_baseline_condition_leaves_the_country_out_and_collapses_to_one_prompt_per_place():
    """The model's own default picture of a place: no country in the sentence, none in the folders."""
    baseline = [name for name, t in conditions(CFG).items() if not names_a_country(t)]
    assert baseline, "no no-country baseline to compare countries against"
    for name in baseline:
        prompts = load_prompts(CFG, condition=name)
        assert {p.iso3 for p in prompts} == {NO_COUNTRY}
        assert len(prompts) == len(CFG["prompts"]["places"])
        assert not any(c["prompt_name"] in prompts[0].text for c in COUNTRIES)


def test_the_light_controlled_condition_pins_the_light_without_naming_a_colour():
    """If it named a colour it would control the grade too, and the comparison would prove nothing."""
    free, noon = conditions(CFG)["free"], conditions(CFG)["noon"]
    assert noon.startswith(free.rstrip(".")), "the control must be the free sentence plus the light"
    added = noon[len(free.rstrip(".")):].lower()
    assert "noon" in added
    for colour in ("warm", "cool", "neutral", "golden", "amber", "blue", "kelvin", "white balance"):
        assert colour not in added, f"the light control must not name a colour: {colour!r}"


def test_the_run_scope_spans_every_income_group():
    income = json.loads((ROOT / CFG["report"]["income_file"]).read_text())
    groups = Counter(income["countries"].get(iso3) for iso3 in CFG["prompts"]["countries"])
    assert None not in groups, "every country in the run needs a World Bank income group"
    assert set(groups) == set(income["labels"]), "every income group must be represented"
    assert max(groups.values()) - min(groups.values()) <= 2, groups


def test_the_run_scope_breaks_the_tie_between_income_and_latitude():
    """Otherwise "warmer" could only ever mean "closer to the equator"."""
    income = json.loads((ROOT / CFG["report"]["income_file"]).read_text())
    latitude = {c["iso_a3"]: abs(c["latitude"]) for c in COUNTRIES}

    def gap(codes: list[str]) -> float:
        by_group: dict[str, list[float]] = {}
        for iso3 in codes:
            by_group.setdefault(income["countries"][iso3], []).append(latitude[iso3])
        means = {g: sum(v) / len(v) for g, v in by_group.items()}
        return means["HIC"] - means["LIC"]

    world = [iso3 for iso3 in latitude if income["countries"].get(iso3)]
    assert gap(CFG["prompts"]["countries"]) < gap(world) / 2

    # And every part of the range holds rich and poor countries, so latitude can be controlled for.
    for low, high in ((0, 20), (20, 90)):
        band = [iso3 for iso3 in CFG["prompts"]["countries"] if low <= latitude[iso3] < high]
        assert len({income["countries"][iso3] for iso3 in band}) == 4, (low, high, band)


def test_every_country_has_a_population():
    """A proxy for how much the model has seen of a country, and the floor on the run's scope."""
    for c in COUNTRIES:
        assert isinstance(c["population"], int) and c["population"] > 0, c


def test_the_run_scope_leaves_out_countries_the_model_can_barely_have_seen():
    """Micro-states balance latitude beautifully and carry none of the stereotypes in question."""
    population = {c["iso_a3"]: c["population"] for c in COUNTRIES}
    too_small = {iso3 for iso3 in CFG["prompts"]["countries"] if population[iso3] < 1_000_000}
    assert not too_small, too_small


def test_the_run_scope_keeps_the_countries_a_reader_will_look_for():
    """A study of how AI pictures countries that omits the obvious ones answers nobody."""
    scope = set(CFG["prompts"]["countries"])
    for iso3 in ("USA", "DEU", "JPN", "BRA", "MEX", "CHN", "IND", "NGA", "EGY", "ETH", "AFG"):
        assert iso3 in scope, iso3


def test_the_run_scope_carries_every_control_it_is_asked_to_hold_constant():
    """A control with a missing value silently drops that country from the controlled tables."""
    by_iso = {c["iso_a3"]: c for c in COUNTRIES}
    for field in CFG["report"]["controls"]:
        missing = [i for i in CFG["prompts"]["countries"] if by_iso[i].get(field) is None]
        assert not missing, f"{field} missing for {missing}"


def test_aridity_is_rainfall_weighed_against_evaporation_not_rainfall_alone():
    """500mm is humid in Norway and desert in Sudan, so rainfall alone is not aridity."""
    by_iso = {c["iso_a3"]: c for c in COUNTRIES}
    for iso3, c in by_iso.items():
        if c["aridity_index"] is not None:
            assert c["aridity_index"] == pytest.approx(
                c["precipitation_mm"] / (c["temperature_c"] + 10), abs=0.06), iso3
    # The index must separate places that rainfall alone ranks together.
    uzb, kaz = by_iso["UZB"], by_iso["KAZ"]
    assert abs(uzb["precipitation_mm"] - kaz["precipitation_mm"]) < 60   # similar rainfall
    assert kaz["aridity_index"] > uzb["aridity_index"] * 1.4            # very different aridity
    assert by_iso["SAU"]["aridity_index"] < 5 < by_iso["NOR"]["aridity_index"]
