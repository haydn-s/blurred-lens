"""Measure every generated image, so one country's pictures can be compared with another's.

    python -m blurred_lens.analyze                    # prompts that have all their images
    python -m blurred_lens.analyze --min-images 20    # also partly generated prompts
    python -m blurred_lens.analyze --force            # measure again even if up to date

Writes outputs/<run>/analysis/<ISO3>/<place>.json -- one row per image, plus a summary of every
metric including the standard error of its mean -- and analysis/index.json, which records what was
measured, which images were left out and why, and the settings used, so a new image or a changed
setting re-measures itself.

Nothing here decides whether a country is graded differently; that comparison belongs to
blurred_lens.report, which reads these files.
"""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from tqdm import tqdm

from .config import ROOT, image_files, load_config, run_dir
from .metrics import METRICS, measure

# Bumped whenever a measurement changes, so old numbers re-measure themselves.
RECIPE_VERSION = 1


def analysis_path(out: Path, iso3: str, place: str) -> Path:
    """Where one prompt's measurements live inside a run folder."""
    return out / "analysis" / iso3 / f"{place}.json"


def recipe(settings: dict) -> dict:
    """Everything that decides the numbers; measurements taken under a different recipe are stale."""
    return {
        "version": RECIPE_VERSION,
        "width": settings["width"],
        "min_spread": settings["min_spread"],
        "metrics": list(METRICS),
    }


def signature(files: list[Path]) -> str:
    """Fingerprint of a prompt's images, so replaced or edited images are measured again."""
    digest = hashlib.sha1()
    for path in files:
        stat = path.stat()
        digest.update(f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}\n".encode())
    return digest.hexdigest()


def read_metadata(folder: Path) -> dict[int, dict]:
    """What generate recorded for each image, keyed by image number."""
    path = folder / "metadata.jsonl"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    return {r["index"]: r for r in records}


def load_image(path: Path, width: int) -> np.ndarray:
    """One image as an (h, w, 3) RGB array at a fixed width.

    Every image is measured at the same size, so a metric that depends on scale -- edge density,
    the haze window -- stays comparable no matter what the model returned.
    """
    with Image.open(path) as img:
        size = (width, round(width * img.height / img.width))
        img.draft("RGB", size)  # lets JPEGs decode straight to a smaller size
        return np.asarray(img.convert("RGB").resize(size, Image.LANCZOS))


def measure_folder(files: list[Path], width: int, min_spread: float) -> tuple[list[dict], dict[str, str]]:
    """Measure a prompt's images one at a time; return the rows and why any were left out.

    Blank frames are the ones worth catching: some models hand back a black or single-color image
    instead of refusing, and its color is not a color the model chose for that country.
    """
    rows: list[dict] = []
    excluded: dict[str, str] = {}
    for path in files:
        try:
            image = load_image(path, width)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            excluded[path.name] = f"unreadable: {str(exc)[:120]}"
            continue
        spread = float(image.std())
        if spread < min_spread:
            excluded[path.name] = f"blank (pixel spread {spread:.1f})"
            continue
        row = {"index": int(path.stem), "file": path.name}
        row.update({name: round(value, 4) for name, value in measure(image).items()})
        rows.append(row)
    return rows, excluded


def summarize(rows: list[dict]) -> dict[str, dict[str, float]]:
    """Every metric's average across a prompt's images, with the spread around it.

    `sem` is the standard error of the mean: the yardstick for whether a gap between two countries
    is bigger than the noise in the sample.
    """
    summary = {}
    for name in METRICS:
        values = np.array([row[name] for row in rows], dtype=np.float64)
        values = values[np.isfinite(values)]
        if values.size == 0:
            continue
        spread = float(values.std(ddof=1)) if values.size > 1 else 0.0
        summary[name] = {
            "mean": round(float(values.mean()), 4),
            "std": round(spread, 4),
            "sem": round(spread / np.sqrt(values.size), 4) if values.size > 1 else 0.0,
            "p05": round(float(np.percentile(values, 5)), 4),
            "p50": round(float(np.percentile(values, 50)), 4),
            "p95": round(float(np.percentile(values, 95)), 4),
            "n": int(values.size),
        }
    return summary


def write_json(payload: dict, path: Path) -> None:
    """Write atomically, so an interrupted run leaves no half-written measurements."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Measure every generated image of every prompt.")
    ap.add_argument("--min-images", type=int, help="images a prompt needs (default: generation.images_per_prompt)")
    ap.add_argument("--run", help="output folder under outputs/ (default: generation.run_name)")
    ap.add_argument("--force", action="store_true", help="measure again even where nothing changed")
    args = ap.parse_args(argv)

    cfg = load_config()
    out = run_dir(cfg, args.run)
    need = args.min_images if args.min_images is not None else cfg["generation"]["images_per_prompt"]
    settings = cfg["analysis"]
    current = recipe(settings)
    folders = sorted(p for p in (out / "images").glob("*/*") if p.is_dir())
    if not folders:
        raise SystemExit(f"No images in {out / 'images'} yet. Run `python -m blurred_lens.generate` first.")

    index_path = out / "analysis" / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    measured = fresh = too_few = left_out = 0
    try:
        for folder in tqdm(folders, unit="prompt"):
            files = image_files(folder)
            if len(files) < need:
                too_few += 1
                continue
            iso3, place = folder.parent.name, folder.name
            key = f"{iso3}/{place}"
            target = analysis_path(out, iso3, place)
            inputs = signature(files)
            entry = index.get(key, {})
            if (not args.force and entry.get("inputs") == inputs and entry.get("recipe") == current
                    and target.exists()):
                fresh += 1
                continue
            rows, excluded = measure_folder(files, settings["width"], settings["min_spread"])
            left_out += len(excluded)
            if not rows:
                tqdm.write(f"{key}: every image was blank or unreadable, skipped")
                continue
            metadata = read_metadata(folder)
            first = next(iter(metadata.values()), {})
            write_json({
                "country": iso3,
                "place": place,
                "run": out.name,
                "prompt": first.get("prompt"),
                "model": first.get("model"),
                "n_images": len(rows),
                "excluded": excluded,
                "summary": summarize(rows),
                "images": rows,
            }, target)
            index[key] = {
                "n_images": len(rows),
                "excluded": excluded,
                "inputs": inputs,
                "recipe": current,
                "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            measured += 1
    finally:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(index, indent=1, sort_keys=True))
    print(f"Measured {measured} prompts · {fresh} already up to date · {too_few} skipped (< {need} images)")
    if left_out:
        print(f"Left {left_out} blank or unreadable images out of the measurements "
              f"(see {os.path.relpath(index_path, ROOT)})")


if __name__ == "__main__":
    main()
