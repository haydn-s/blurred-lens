"""Project paths, config.toml loading, and the on-disk layout shared by every step."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Images are numbered 0001.jpg, 0002.jpg, ... inside outputs/<run>/images/<ISO3>/<place>/.
IMAGE_RE = re.compile(r"^(\d{4})\.(jpg|png|webp)$")


def load_config(path: Path = ROOT / "config.toml") -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def run_dir(cfg: dict, run: str | None = None) -> Path:
    """outputs/<run_name>/ -- one folder per model/prompt setup, so runs never mix."""
    return ROOT / cfg["paths"]["outputs_dir"] / (run or cfg["generation"]["run_name"])


def image_files(folder: Path) -> list[Path]:
    """The numbered images in one prompt's folder, in index order."""
    if not folder.is_dir():
        return []
    return sorted(f for f in folder.iterdir() if IMAGE_RE.match(f.name))
