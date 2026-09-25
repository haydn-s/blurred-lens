"""Bundle composites, sample images and prompts into web/data/ for the globe website.

    python -m blurred_lens.export_site
    python -m http.server --directory web 8000      # then open http://localhost:8000

Every country and place is listed even before any images exist, so the site works at
every stage of generation: prompts without composites show as "not generated yet".

An image is re-encoded whenever its source file or the export settings change, and images this
export didn't write are deleted, so web/data always shows the run named in the manifest and never
a leftover from an earlier one.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from .composite import composite_path
from .config import ROOT, image_files, load_config, run_dir
from .prompts import format_prompt, load_json

JPEG_QUALITY = 85
SOURCES_FILE = "sources.json"  # what each exported image was made from; the website never reads it


class Exporter:
    """Writes web-sized JPEGs into `site`, skipping work an earlier export already did."""

    def __init__(self, site: Path):
        self.site = site
        path = site / SOURCES_FILE
        self.previous: dict[str, dict] = json.loads(path.read_text()) if path.exists() else {}
        self.current: dict[str, dict] = {}

    def jpeg(self, src: Path, rel: str, max_side: int | None = None) -> str:
        """Export `src` to `rel` inside the site folder, and return `rel`."""
        stat = src.stat()
        # Relative to the project, both so the site never carries local paths and so moving the
        # project doesn't invalidate every image.
        recipe = {"source": os.path.relpath(src, ROOT), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                  "max_side": max_side, "quality": JPEG_QUALITY}
        dest = self.site / rel
        if self.previous.get(rel) != recipe or not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(src) as img:
                img = img.convert("RGB")
                if max_side:
                    img.thumbnail((max_side, max_side))
                img.save(dest, "JPEG", quality=JPEG_QUALITY)
        self.current[rel] = recipe
        return rel

    def finish(self) -> int:
        """Delete images this export didn't write, and record what it did write."""
        removed = 0
        for folder in ("composites", "samples"):
            root = self.site / folder
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*"), reverse=True):  # deepest first, so folders empty out
                if path.is_file() and path.relative_to(self.site).as_posix() not in self.current:
                    path.unlink()
                    removed += 1
                elif path.is_dir() and not any(path.iterdir()):
                    path.rmdir()
        self.site.mkdir(parents=True, exist_ok=True)
        (self.site / SOURCES_FILE).write_text(json.dumps(self.current, indent=1, sort_keys=True))
        return removed


def read_metadata(folder: Path) -> dict[int, dict]:
    path = folder / "metadata.jsonl"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    return {r["index"]: r for r in records}


def build_site_data(cfg: dict, out: Path, site: Path) -> tuple[dict, int]:
    """Copy web-sized images from run folder `out` into `site`; return the manifest and how many
    stale images were removed."""
    index_path = out / "composites" / "index.json"
    built = json.loads(index_path.read_text()) if index_path.exists() else {}
    template = cfg["prompts"]["template"]
    n_samples, thumb = cfg["site"]["samples_per_prompt"], cfg["site"]["thumbnail_size"]
    places = load_json(cfg["prompts"]["places_file"])
    exporter = Exporter(site)

    countries = []
    for c in load_json(cfg["prompts"]["countries_file"]):
        iso3, entries = c["iso_a3"], []
        for p in places:
            entry = {
                "place": p["id"],
                "prompt": format_prompt(template, c, p),
                "model": None,
                "n_images": 0,
                "effective_images": 0,
                "composite": None,  # stays None until the prompt's composite is built
                "samples": [],
            }
            key = f"{iso3}/{p['id']}"
            source = composite_path(out, iso3, p["id"])
            if key in built and source.exists():
                record = built[key]
                folder = out / "images" / iso3 / p["id"]
                meta = read_metadata(folder)
                first = next(iter(meta.values()), {})
                entry.update(prompt=first.get("prompt") or entry["prompt"], model=first.get("model"),
                             n_images=record["n_images"],
                             effective_images=record.get("effective_images", 0),
                             composite=exporter.jpeg(source, f"composites/{iso3}/{p['id']}.jpg"))
                # Images the blend left out aren't "images behind this composite", so don't show them.
                excluded = record.get("excluded", {})
                usable = [f for f in image_files(folder) if f.name not in excluded]
                for f in usable[:n_samples]:
                    rel = exporter.jpeg(f, f"samples/{iso3}/{p['id']}/{f.stem}.jpg", thumb)
                    revised = meta.get(int(f.stem), {}).get("revised_prompt")
                    entry["samples"].append({"image": rel, "revised_prompt": revised})
            entries.append(entry)
        countries.append({
            "iso3": iso3, "iso_num": c["iso_num"], "name": c["name"],
            "region": c["region"], "subregion": c["subregion"], "entries": entries,
        })

    manifest = {
        "run": out.name,
        "template": template,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "places": [{"id": p["id"], "label": p["label"]} for p in places],
        "countries": countries,
    }
    return manifest, exporter.finish()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Build web/data/ for the globe website.")
    ap.add_argument("--run", help="output folder under outputs/ (default: generation.run_name)")
    args = ap.parse_args(argv)

    cfg = load_config()
    site = ROOT / cfg["paths"]["site_data_dir"]
    manifest, removed = build_site_data(cfg, run_dir(cfg, args.run), site)
    site.mkdir(parents=True, exist_ok=True)
    (site / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
                                        encoding="utf-8")
    entries = [e for c in manifest["countries"] for e in c["entries"]]
    done = sum(e["composite"] is not None for e in entries)
    print(f"Exported {done:,} of {len(entries):,} prompts with composites -> {site}")
    if removed:
        print(f"Removed {removed:,} image(s) an earlier export had left behind")


if __name__ == "__main__":
    main()
