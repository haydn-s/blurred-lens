import pytest

from blurred_lens.config import load_config
from blurred_lens.prompts import build_prompts, load_json, load_prompts, select

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
    assert len(load_prompts(CFG)) == len(COUNTRIES) * len(PLACES)


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
