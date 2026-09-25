import json
import os
import time

from PIL import Image

from blurred_lens.config import load_config
from blurred_lens.export_site import build_site_data
from blurred_lens.prompts import format_prompt, load_json, template_for

CFG = load_config()
PLACES = load_json(CFG["prompts"]["places_file"])
PLACE = PLACES[0]["id"]


def country(manifest, iso3):
    return next(c for c in manifest["countries"] if c["iso3"] == iso3)


def make_run(root, color, *, mtime=None, n_images=2, excluded=None, metrics=None):
    """A run folder with generated images and measurements for FRA's first place."""
    folder = root / "images" / "FRA" / PLACE
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(1, n_images + 1):
        Image.new("RGB", (64, 64), color).save(folder / f"{i:04d}.jpg")
    (folder / "metadata.jsonl").write_text(
        json.dumps({"index": 1, "prompt": "p", "model": "m", "revised_prompt": "r"}) + "\n")

    summary = {name: {"mean": value, "std": 0.0, "sem": 0.0, "p05": value, "p50": value, "p95": value,
                      "n": n_images}
               for name, value in (metrics or {"cast_b": 3.5, "haze": 0.2}).items()}
    measurements = root / "analysis" / "FRA" / f"{PLACE}.json"
    measurements.parent.mkdir(parents=True, exist_ok=True)
    measurements.write_text(json.dumps({
        "country": "FRA", "place": PLACE, "prompt": "p", "model": "m", "n_images": n_images,
        "excluded": excluded or {}, "summary": summary, "images": []}))
    (root / "analysis" / "index.json").write_text(json.dumps(
        {f"FRA/{PLACE}": {"n_images": n_images, "excluded": excluded or {}}}))

    if mtime is not None:
        for path in root.rglob("*"):
            if path.is_file():
                os.utime(path, (mtime, mtime))


def test_every_prompt_is_listed_before_any_images_exist(tmp_path):
    manifest, removed = build_site_data(CFG, tmp_path / "run", tmp_path / "site")

    usa = country(manifest, "USA")
    assert len(manifest["countries"]) == len(load_json(CFG["prompts"]["countries_file"]))
    assert [e["metrics"] for e in usa["entries"]] == [None] * len(PLACES)
    template = template_for(CFG)[1]
    first = format_prompt(template, {"prompt_name": "the United States"}, PLACES[0])
    assert (usa["entries"][0]["prompt"], removed, manifest["metric"]) == (first, 0, None)


def test_measurements_and_samples_are_exported(tmp_path):
    out, site = tmp_path / "run", tmp_path / "site"
    make_run(out, (180, 40, 40))

    entry = country(build_site_data(CFG, out, site)[0], "FRA")["entries"][0]

    assert (entry["prompt"], entry["model"], entry["n_images"]) == ("p", "m", 2)
    assert entry["metrics"] == {"cast_b": 3.5, "haze": 0.2}
    assert [s["revised_prompt"] for s in entry["samples"]] == ["r", None]
    assert all((site / s["image"]).is_file() for s in entry["samples"])


def test_the_report_adds_rankings(tmp_path):
    out, site = tmp_path / "run", tmp_path / "site"
    make_run(out, (180, 40, 40))
    (out / "analysis" / "report.json").write_text(json.dumps({
        "metric": "cast_b", "metric_label": "yellow-blue cast (higher is more yellow)",
        "countries": {"FRA": {"index": 1.25, "income": "High income", "places": {PLACE: {"z": 1.4}}}}}))

    manifest = build_site_data(CFG, out, site)[0]

    france = country(manifest, "FRA")
    assert manifest["metric"]["name"] == "cast_b"
    assert (france["index"], france["income"]) == (1.25, "High income")
    assert france["entries"][0]["z"] == 1.4


def test_exporting_another_run_replaces_the_sites_images(tmp_path):
    """The site used to keep the older run's pixels whenever its files were older than the export."""
    now = time.time()
    make_run(tmp_path / "v1", (255, 0, 0), mtime=now - 7200)
    make_run(tmp_path / "v2", (0, 0, 255), mtime=now - 3600)
    site = tmp_path / "site"

    build_site_data(CFG, tmp_path / "v1", site)
    entry = country(build_site_data(CFG, tmp_path / "v2", site)[0], "FRA")["entries"][0]

    with Image.open(site / entry["samples"][0]["image"]) as img:
        assert img.getpixel((0, 0))[2] > 200, "the sample still shows run v1"


def test_images_the_manifest_no_longer_names_are_deleted(tmp_path):
    out, site = tmp_path / "run", tmp_path / "site"
    make_run(out, (180, 40, 40))
    stale = site / country(build_site_data(CFG, out, site)[0], "FRA")["entries"][0]["samples"][0]["image"]

    (out / "analysis" / "index.json").write_text("{}")  # nothing measured any more
    manifest, removed = build_site_data(CFG, out, site)

    assert not stale.exists() and removed >= 1
    assert country(manifest, "FRA")["entries"][0]["metrics"] is None


def test_a_new_thumbnail_size_is_honoured(tmp_path):
    out, site = tmp_path / "run", tmp_path / "site"
    make_run(out, (180, 40, 40))
    build_site_data(CFG, out, site)

    smaller = load_config()
    smaller["site"]["thumbnail_size"] = 32
    entry = country(build_site_data(smaller, out, site)[0], "FRA")["entries"][0]

    with Image.open(site / entry["samples"][0]["image"]) as img:
        assert img.size == (32, 32)


def test_images_the_measurements_left_out_are_not_shown(tmp_path):
    out, site = tmp_path / "run", tmp_path / "site"
    make_run(out, (180, 40, 40), n_images=3, excluded={"0001.jpg": "blank (pixel spread 0.0)"})

    entry = country(build_site_data(CFG, out, site)[0], "FRA")["entries"][0]

    assert [s["image"].rsplit("/", 1)[1] for s in entry["samples"]] == ["0002.jpg", "0003.jpg"]
