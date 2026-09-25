"""Build the prompt matrix: one prompt per (country, place) pair, under one condition.

A *condition* is a prompt template. The same countries and places are generated under each one,
and each condition writes to its own run folder, so images made from different sentences can never
end up in the same average:

    free            "A photograph of {place} in {country}, {view}."
    noon            the same, with the time of day and the sun's height pinned
    baseline        the country left out, so every country can be read as a deviation from the
                    model's own default picture of a place
    baseline_noon   the baseline under the same pinned light

A template without a `{country}` slot is a baseline: it collapses the country dimension to a single
prompt per place, filed under NO_COUNTRY so it never sits among the countries being compared.
"""

import json
from dataclasses import dataclass

from .config import ROOT

# Folder (and `country` field) for prompts that name no country. Deliberately not an ISO 3166-1
# code: nothing in data/countries.json carries it, so the baseline never joins the country
# rankings or the globe, and its measurements sit in their own folder next to theirs.
NO_COUNTRY = "_none"


@dataclass(frozen=True)
class Prompt:
    iso3: str   # ISO 3166-1 alpha-3 country code, e.g. "FRA", or NO_COUNTRY for a baseline prompt
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


def conditions(cfg: dict) -> dict[str, str]:
    """Every named condition in config.toml: name -> template."""
    named = cfg["prompts"].get("conditions") or {}
    if not named:
        raise ValueError("no [prompts.conditions] in config.toml: a run needs at least one template")
    return dict(named)


def template_for(cfg: dict, condition: str | None = None) -> tuple[str, str]:
    """The (name, template) of one condition, defaulting to prompts.condition."""
    named = conditions(cfg)
    name = condition or cfg["prompts"]["condition"]
    if name not in named:
        raise ValueError(f"unknown condition {name!r}: choose one of {', '.join(sorted(named))}")
    return name, named[name]


def names_a_country(template: str) -> bool:
    """False for a baseline template, which leaves the country out of the sentence."""
    return "{country}" in template


def format_prompt(template: str, country: dict, place: dict) -> str:
    """The exact text sent to the model for one (country, place) pair."""
    return template.format(country=country.get("prompt_name", ""), place=place["phrase"],
                           view=place.get("view", ""))


def build_prompts(countries: list[dict], places: list[dict], template: str) -> list[Prompt]:
    """One prompt per (country, place); or one per place when the template names no country."""
    if not names_a_country(template):
        return [Prompt(NO_COUNTRY, p["id"], format_prompt(template, {}, p)) for p in places]
    return [Prompt(c["iso_a3"], p["id"], format_prompt(template, c, p)) for c in countries for p in places]


def load_prompts(cfg: dict, countries: list[str] | None = None, places: list[str] | None = None,
                 condition: str | None = None) -> list[Prompt]:
    """Every prompt in the run's scope: the caller's lists, else prompts.countries / prompts.places."""
    pc = cfg["prompts"]
    _, template = template_for(cfg, condition)
    return build_prompts(
        select(load_json(pc["countries_file"]), countries or pc.get("countries"), "iso_a3"),
        select(load_json(pc["places_file"]), places or pc.get("places"), "id"),
        template,
    )
