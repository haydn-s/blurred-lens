import json

from PIL import Image

from blurred_lens.config import load_config
from blurred_lens.export_site import build_site_data
from blurred_lens.prompts import load_json

CFG = load_config()
PLACES = load_json(CFG["prompts"]["places_file"])


def country(manifest, iso3):
    return next(c for c in manifest["countries"] if c["iso3"] == iso3)


def test_every_prompt_is_listed_before_any_images_exist(tmp_path):
    manifest = build_site_data(CFG, tmp_path / "run", tmp_path / "site")

    usa = country(manifest, "USA")
    assert len(manifest["countries"]) == len(load_json(CFG["prompts"]["countries_file"]))
    assert [e["composites"] for e in usa["entries"]] == [None] * len(PLACES)
    first = CFG["prompts"]["template"].format(place=PLACES[0]["phrase"], country="the United States")
    assert usa["entries"][0]["prompt"] == first


def test_built_composites_and_samples_are_exported(tmp_path):
    out, site = tmp_path / "run", tmp_path / "site"
    place = PLACES[0]["id"]
    folder = out / "images" / "FRA" / place
    folder.mkdir(parents=True)
    for i in (1, 2):
        Image.new("RGB", (64, 64), (i * 60, 0, 0)).save(folder / f"{i:04d}.jpg")
    (folder / "metadata.jsonl").write_text(
        json.dumps({"index": 1, "prompt": "p", "model": "m", "revised_prompt": "r"}) + "\n")
    (out / "composites" / "FRA").mkdir(parents=True)
    for method in ("mean", "median"):
        Image.new("RGB", (64, 64)).save(out / "composites" / "FRA" / f"{place}_{method}.png")
    (out / "composites" / "index.json").write_text(json.dumps({f"FRA/{place}": {"n_images": 2}}))

    entry = country(build_site_data(CFG, out, site), "FRA")["entries"][0]

    assert (entry["prompt"], entry["model"], entry["n_images"]) == ("p", "m", 2)
    assert (site / entry["composites"]["mean"]).is_file()
    assert [s["revised_prompt"] for s in entry["samples"]] == ["r", None]
    assert all((site / s["image"]).is_file() for s in entry["samples"])
