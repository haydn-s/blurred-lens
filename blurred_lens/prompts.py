"""Build the prompt matrix: one prompt per (country, place) pair."""

import json
from dataclasses import dataclass

from .config import ROOT


@dataclass(frozen=True)
class Prompt:
    iso3: str   # ISO 3166-1 alpha-3 country code, e.g. "FRA"
    place: str  # place id from places.json, e.g. "city"
    text: str   # the exact text sent to the model


def load_json(relpath: str) -> list[dict]:
    with open(ROOT / relpath, encoding="utf-8") as f:
        return json.load(f)


def select(items: list[dict], wanted: list[str] | None, key: str) -> list[dict]:
    """Items whose `key` is in `wanted` (every item when wanted is empty). Typos are an error."""
    if not wanted:
        return items
    unknown = set(wanted) - {item[key] for item in items}
    if unknown:
        raise ValueError(f"unknown {key}: {', '.join(sorted(unknown))}")
    return [item for item in items if item[key] in wanted]


def format_prompt(template: str, country: dict, place: dict) -> str:
    """The exact text sent to the model for one (country, place) pair."""
    return template.format(country=country["prompt_name"], place=place["phrase"], view=place.get("view", ""))


def build_prompts(countries: list[dict], places: list[dict], template: str) -> list[Prompt]:
    return [Prompt(c["iso_a3"], p["id"], format_prompt(template, c, p)) for c in countries for p in places]


def load_prompts(cfg: dict, countries: list[str] | None = None, places: list[str] | None = None) -> list[Prompt]:
    pc = cfg["prompts"]
    return build_prompts(
        select(load_json(pc["countries_file"]), countries, "iso_a3"),
        select(load_json(pc["places_file"]), places, "id"),
        pc["template"],
    )
