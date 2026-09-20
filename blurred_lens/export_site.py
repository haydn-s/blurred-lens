"""Bundle composites, sample images and prompts into web/data/ for the globe website.

    python -m blurred_lens.export_site
    python -m http.server --directory web 8000      # then open http://localhost:8000

Every country and place is listed even before any images exist, so the site works at
every stage of generation: prompts without composites show as "not generated yet".
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from .config import ROOT, image_files, load_config, run_dir
from .prompts import format_prompt, load_json

METHODS = ("mean", "median")


def export_jpeg(src: Path, dest: Path, max_side: int | None = None) -> None:
    """Re-encode `src` as a web-sized JPEG; skipped when `dest` is already newer."""
    if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        img = img.convert("RGB")
        if max_side:
            img.thumbnail((max_side, max_side))
        img.save(dest, "JPEG", quality=85)


def read_metadata(folder: Path) -> dict[int, dict]:
    path = folder / "metadata.jsonl"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    return {r["index"]: r for r in records}


def build_site_data(cfg: dict, out: Path, site: Path) -> dict:
    """Copy web-sized images from run folder `out` into `site` and return the manifest."""
    index_path = out / "composites" / "index.json"
    built = json.loads(index_path.read_text()) if index_path.exists() else {}
    template = cfg["prompts"]["template"]
    n_samples, thumb = cfg["site"]["samples_per_prompt"], cfg["site"]["thumbnail_size"]
    places = load_json(cfg["prompts"]["places_file"])

    countries = []
    for c in load_json(cfg["prompts"]["countries_file"]):
        iso3, entries = c["iso_a3"], []
        for p in places:
            entry = {
                "place": p["id"],
                "prompt": format_prompt(template, c, p),
                "model": None,
                "n_images": 0,
                "composites": None,  # stays None until the prompt's composites are built
                "samples": [],
            }
            key = f"{iso3}/{p['id']}"
            sources = {m: out / "composites" / iso3 / f"{p['id']}_{m}.png" for m in METHODS}
            if key in built and all(s.exists() for s in sources.values()):
                folder = out / "images" / iso3 / p["id"]
                meta = read_metadata(folder)
                first = next(iter(meta.values()), {})
                entry.update(prompt=first.get("prompt") or entry["prompt"], model=first.get("model"),
                             n_images=built[key]["n_images"], composites={})
                for method, src in sources.items():
                    rel = f"composites/{iso3}/{p['id']}_{method}.jpg"
                    export_jpeg(src, site / rel)
                    entry["composites"][method] = rel
                for f in image_files(folder)[:n_samples]:
                    rel = f"samples/{iso3}/{p['id']}/{f.stem}.jpg"
                    export_jpeg(f, site / rel, thumb)
                    revised = meta.get(int(f.stem), {}).get("revised_prompt")
                    entry["samples"].append({"image": rel, "revised_prompt": revised})
            entries.append(entry)
        countries.append({
            "iso3": iso3, "iso_num": c["iso_num"], "name": c["name"],
            "region": c["region"], "subregion": c["subregion"], "entries": entries,
        })

    return {
        "run": out.name,
        "template": template,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "places": [{"id": p["id"], "label": p["label"]} for p in places],
        "countries": countries,
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Build web/data/ for the globe website.")
    ap.add_argument("--run", help="output folder under outputs/ (default: generation.run_name)")
    args = ap.parse_args(argv)

    cfg = load_config()
    site = ROOT / cfg["paths"]["site_data_dir"]
    manifest = build_site_data(cfg, run_dir(cfg, args.run), site)
    site.mkdir(parents=True, exist_ok=True)
    (site / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
                                        encoding="utf-8")
    entries = [e for c in manifest["countries"] for e in c["entries"]]
    done = sum(e["composites"] is not None for e in entries)
    print(f"Exported {done:,} of {len(entries):,} prompts with composites -> {site}")


if __name__ == "__main__":
    main()
