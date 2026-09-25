"""Blend each prompt's images into one composite: the picture the model tends to draw.

    python -m blurred_lens.composite                  # prompts that have all their images
    python -m blurred_lens.composite --min-images 20  # also partly generated prompts
    python -m blurred_lens.composite --force          # rebuild even if up to date

Writes outputs/<run>/composites/<ISO3>/<place>.png, plus composites/index.json recording how each
composite was built: how many images went in, which were left out and why, how many images the
blend effectively leant on, and the settings used. A composite is rebuilt whenever its images or
those settings change, so changing the blend in config.toml is enough to refresh a run.
"""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from tqdm import tqdm

from .blend import blend_typical, effective_count
from .config import ROOT, image_files, load_config, run_dir

# Bumped whenever the blending itself changes, so old composites rebuild themselves.
RECIPE_VERSION = 1


def composite_path(out: Path, iso3: str, place: str) -> Path:
    """Where one prompt's composite lives inside a run folder."""
    return out / "composites" / iso3 / f"{place}.png"


def recipe(settings: dict) -> dict:
    """Everything about how a composite is made; a composite whose recipe differs is out of date."""
    return {
        "version": RECIPE_VERSION,
        "method": "typicality-weighted alpha blend",
        "width": settings["width"],
        "bandwidth": settings["bandwidth"],
        "iterations": settings["iterations"],
        "min_spread": settings["min_spread"],
    }


def signature(files: list[Path]) -> str:
    """Fingerprint of a prompt's images, so replaced or edited images rebuild the composite."""
    digest = hashlib.sha1()
    for path in files:
        stat = path.stat()
        digest.update(f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}\n".encode())
    return digest.hexdigest()


def load_images(files: list[Path], width: int, min_spread: float) -> tuple[list[np.ndarray], dict[str, str]]:
    """Every usable image as an (h, w, 3) RGB array, plus why the rest were left out.

    Blank frames are the ones worth catching: some models hand back a black or single-colour image
    instead of refusing a prompt, and averaged in silently they would just darken the composite.
    """
    images: list[np.ndarray] = []
    excluded: dict[str, str] = {}
    size: tuple[int, int] | None = None
    for path in files:
        try:
            with Image.open(path) as img:
                if size is None:  # the first image sets the shape; the rest are cropped to match
                    size = (width, round(width * img.height / img.width))
                img.draft("RGB", size)  # lets JPEGs decode straight to a smaller size
                array = np.asarray(ImageOps.fit(img.convert("RGB"), size))
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            excluded[path.name] = f"unreadable: {str(exc)[:120]}"
            continue
        spread = float(array.std())
        if spread < min_spread:
            excluded[path.name] = f"blank (pixel spread {spread:.1f})"
            continue
        images.append(array)
    return images, excluded


def save_png(image: Image.Image, path: Path) -> None:
    """Write atomically, so an interrupted run can never leave half a composite behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    image.save(tmp, "PNG")
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Blend each prompt's images into one composite.")
    ap.add_argument("--min-images", type=int, help="images a prompt needs (default: generation.images_per_prompt)")
    ap.add_argument("--run", help="output folder under outputs/ (default: generation.run_name)")
    ap.add_argument("--force", action="store_true", help="rebuild composites that are already up to date")
    args = ap.parse_args(argv)

    cfg = load_config()
    out = run_dir(cfg, args.run)
    need = args.min_images if args.min_images is not None else cfg["generation"]["images_per_prompt"]
    settings = cfg["composite"]
    current = recipe(settings)
    folders = sorted(p for p in (out / "images").glob("*/*") if p.is_dir())
    if not folders:
        raise SystemExit(f"No images in {out / 'images'} yet. Run `python -m blurred_lens.generate` first.")

    index_path = out / "composites" / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    built = fresh = too_few = left_out = 0
    try:
        for folder in tqdm(folders, unit="prompt"):
            files = image_files(folder)
            if len(files) < need:
                too_few += 1
                continue
            key = f"{folder.parent.name}/{folder.name}"
            target = composite_path(out, folder.parent.name, folder.name)
            inputs = signature(files)
            entry = index.get(key, {})
            if (not args.force and entry.get("inputs") == inputs and entry.get("recipe") == current
                    and target.exists()):
                fresh += 1
                continue
            images, excluded = load_images(files, settings["width"], settings["min_spread"])
            left_out += len(excluded)
            if not images:
                tqdm.write(f"{key}: every image was blank or unreadable, skipped")
                continue
            blended, weights = blend_typical(images, settings["bandwidth"], settings["iterations"])
            save_png(Image.fromarray(blended), target)
            index[key] = {
                "n_images": len(images),
                "effective_images": round(effective_count(weights), 1),
                "excluded": excluded,
                "inputs": inputs,
                "recipe": current,
                "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            built += 1
    finally:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(index, indent=1, sort_keys=True))
    print(f"Blended {built} composites · {fresh} already up to date · {too_few} prompts skipped (< {need} images)")
    if left_out:
        print(f"Left {left_out} blank or unreadable images out of the blends "
              f"(see {os.path.relpath(index_path, ROOT)})")


if __name__ == "__main__":
    main()
