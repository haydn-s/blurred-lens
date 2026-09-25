import json

import cv2
import numpy as np
from PIL import Image

from blurred_lens import analyze
from blurred_lens.config import load_config

KEY = "AAA/city"


def photo(path, seed):
    rng = np.random.default_rng(seed)
    small = rng.integers(40, 220, (8, 8, 3), dtype=np.uint8)
    Image.fromarray(cv2.resize(small, (64, 64), interpolation=cv2.INTER_LINEAR)).save(path)


def setup_run(tmp_path, monkeypatch, images=2):
    """A run folder with one prompt, and a config pointing the pipeline at it."""
    cfg = load_config()
    cfg["paths"]["outputs_dir"] = str(tmp_path)  # absolute, so run_dir ignores the project root
    cfg["generation"]["run_name"] = "test"
    cfg["generation"]["images_per_prompt"] = 2
    cfg["analysis"]["width"] = 64
    monkeypatch.setattr(analyze, "load_config", lambda: cfg)
    folder = tmp_path / "test" / "images" / "AAA" / "city"
    folder.mkdir(parents=True)
    for i in range(1, images + 1):
        photo(folder / f"{i:04d}.png", seed=i)
    return cfg, folder


def read_index(tmp_path):
    return json.loads((tmp_path / "test" / "analysis" / "index.json").read_text())


def read_measurements(tmp_path):
    return json.loads((tmp_path / "test" / "analysis" / "AAA" / "city.json").read_text())


def test_every_image_is_measured_and_summarized(tmp_path, monkeypatch, capsys):
    setup_run(tmp_path, monkeypatch)

    analyze.main([])

    measurements = read_measurements(tmp_path)
    assert measurements["n_images"] == 2
    assert len(measurements["images"]) == 2
    assert {"mean", "std", "sem", "p05", "p50", "p95", "n"} <= set(measurements["summary"]["cast_b"])
    assert measurements["summary"]["cast_b"]["n"] == 2
    assert read_index(tmp_path)[KEY]["recipe"]["version"] == analyze.RECIPE_VERSION
    assert "Measured 1 prompts" in capsys.readouterr().out


def test_blank_frames_are_left_out(tmp_path, monkeypatch, capsys):
    _, folder = setup_run(tmp_path, monkeypatch)
    Image.new("RGB", (64, 64), (0, 0, 0)).save(folder / "0003.png")

    analyze.main([])

    assert "blank" in read_index(tmp_path)[KEY]["excluded"]["0003.png"]
    assert read_measurements(tmp_path)["n_images"] == 2
    assert "Left 1 blank or unreadable images" in capsys.readouterr().out


def test_unreadable_images_do_not_stop_the_run(tmp_path, monkeypatch):
    _, folder = setup_run(tmp_path, monkeypatch)
    (folder / "0003.png").write_bytes(b"not an image")

    analyze.main([])

    assert "unreadable" in read_index(tmp_path)[KEY]["excluded"]["0003.png"]


def test_measurements_are_not_repeated(tmp_path, monkeypatch, capsys):
    setup_run(tmp_path, monkeypatch)
    analyze.main([])
    capsys.readouterr()

    analyze.main([])

    assert "Measured 0 prompts · 1 already up to date" in capsys.readouterr().out


def test_a_changed_setting_re_measures(tmp_path, monkeypatch, capsys):
    cfg, _ = setup_run(tmp_path, monkeypatch)
    analyze.main([])
    capsys.readouterr()

    cfg["analysis"]["width"] = 32
    analyze.main([])

    assert "Measured 1 prompts" in capsys.readouterr().out
    assert read_index(tmp_path)[KEY]["recipe"]["width"] == 32


def test_a_replaced_image_re_measures(tmp_path, monkeypatch, capsys):
    _, folder = setup_run(tmp_path, monkeypatch)
    analyze.main([])
    capsys.readouterr()

    photo(folder / "0002.png", seed=99)  # same file count, different picture
    analyze.main([])

    assert "Measured 1 prompts" in capsys.readouterr().out


def test_prompts_without_enough_images_are_skipped(tmp_path, monkeypatch, capsys):
    setup_run(tmp_path, monkeypatch, images=1)

    analyze.main([])

    assert "1 skipped" in capsys.readouterr().out
    assert read_index(tmp_path) == {}
