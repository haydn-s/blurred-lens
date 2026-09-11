"""Condense each prompt's images into one "average" image: the pixel-wise mean and median.

    python -m blurred_lens.composite                  # prompts that have all their images
    python -m blurred_lens.composite --min-images 20  # also partly generated prompts
    python -m blurred_lens.composite --force          # rebuild even if up to date

Writes outputs/<run>/composites/<ISO3>/<place>_mean.png and <place>_median.png, plus
composites/index.json recording how many images went into each composite.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from tqdm import tqdm

from .config import image_files, load_config, run_dir

METHODS = ("mean", "median")


def load_stack(files: list[Path], width: int) -> np.ndarray:
    """All images as one (N, height, width, 3) uint8 array, resized to `width` pixels wide."""
    with Image.open(files[0]) as first:
        height = round(width * first.height / first.width)
    stack = np.empty((len(files), height, width, 3), dtype=np.uint8)
    for i, path in enumerate(files):
        with Image.open(path) as img:
            img.draft("RGB", (width, height))  # lets JPEGs decode straight to a smaller size
            stack[i] = np.asarray(ImageOps.fit(img.convert("RGB"), (width, height)))
    return stack


def make_composites(files: list[Path], width: int) -> dict[str, Image.Image]:
    stack = load_stack(files, width)
    return {
        "mean": Image.fromarray(stack.mean(axis=0).round().astype(np.uint8)),
        "median": Image.fromarray(np.median(stack, axis=0).round().astype(np.uint8)),
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Average each prompt's images into composites.")
    ap.add_argument("--min-images", type=int, help="images a prompt needs (default: generation.images_per_prompt)")
    ap.add_argument("--run", help="output folder under outputs/ (default: generation.run_name)")
    ap.add_argument("--force", action="store_true", help="rebuild composites that are already up to date")
    args = ap.parse_args(argv)

    cfg = load_config()
    out = run_dir(cfg, args.run)
    need = args.min_images or cfg["generation"]["images_per_prompt"]
    width = cfg["composite"]["width"]
    folders = sorted(p for p in (out / "images").glob("*/*") if p.is_dir())
    if not folders:
        raise SystemExit(f"No images in {out / 'images'} yet. Run `python -m blurred_lens.generate` first.")

    index_path = out / "composites" / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    built = current = too_few = 0
    try:
        for folder in tqdm(folders, unit="prompt"):
            files = image_files(folder)
            if len(files) < need:
                too_few += 1
                continue
            key = f"{folder.parent.name}/{folder.name}"
            targets = {m: out / "composites" / folder.parent.name / f"{folder.name}_{m}.png" for m in METHODS}
            entry = index.get(key, {})
            if (not args.force and entry.get("n_images") == len(files) and entry.get("width") == width
                    and all(t.exists() for t in targets.values())):
                current += 1
                continue
            targets["mean"].parent.mkdir(parents=True, exist_ok=True)
            for method, img in make_composites(files, width).items():
                img.save(targets[method])
            index[key] = {
                "n_images": len(files),
                "width": width,
                "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            built += 1
    finally:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(index, indent=1, sort_keys=True))
    print(f"Built {built} composites · {current} already up to date · {too_few} prompts skipped (< {need} images)")


if __name__ == "__main__":
    main()
