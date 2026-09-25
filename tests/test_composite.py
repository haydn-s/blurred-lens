import json

import numpy as np
from PIL import Image

from blurred_lens import composite
from blurred_lens.config import load_config

KEY = "AAA/city"


def noisy(path, seed):
    """A textured image, the way a generated photo is textured (a flat one counts as blank)."""
    rng = np.random.default_rng(seed)
    Image.fromarray(rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)).save(path)


def setup_run(tmp_path, monkeypatch, colours=2):
    """A run folder with one prompt, and a config pointing the pipeline at it."""
    cfg = load_config()
    cfg["paths"]["outputs_dir"] = str(tmp_path)  # absolute, so run_dir ignores the project root
    cfg["generation"]["run_name"] = "test"
    cfg["generation"]["images_per_prompt"] = 2
    monkeypatch.setattr(composite, "load_config", lambda: cfg)
    folder = tmp_path / "test" / "images" / "AAA" / "city"
    folder.mkdir(parents=True)
    for i in range(1, colours + 1):
        noisy(folder / f"{i:04d}.png", seed=i)
    return cfg, folder


def read_index(tmp_path):
    return json.loads((tmp_path / "test" / "composites" / "index.json").read_text())


def test_a_composite_is_written_and_indexed(tmp_path, monkeypatch, capsys):
    setup_run(tmp_path, monkeypatch)

    composite.main([])

    assert (tmp_path / "test" / "composites" / "AAA" / "city.png").is_file()
    entry = read_index(tmp_path)[KEY]
    assert (entry["n_images"], entry["excluded"]) == (2, {})
    assert entry["recipe"]["version"] == composite.RECIPE_VERSION
    assert "Blended 1 composites" in capsys.readouterr().out


def test_blank_images_are_left_out(tmp_path, monkeypatch, capsys):
    _, folder = setup_run(tmp_path, monkeypatch)
    Image.new("RGB", (64, 64), (0, 0, 0)).save(folder / "0003.png")

    composite.main([])

    entry = read_index(tmp_path)[KEY]
    assert entry["n_images"] == 2
    assert "blank" in entry["excluded"]["0003.png"]
    assert "Left 1 blank or unreadable images" in capsys.readouterr().out


def test_unreadable_images_are_left_out_instead_of_stopping_the_run(tmp_path, monkeypatch):
    _, folder = setup_run(tmp_path, monkeypatch)
    (folder / "0003.png").write_bytes(b"not an image")

    composite.main([])

    assert "unreadable" in read_index(tmp_path)[KEY]["excluded"]["0003.png"]


def test_an_up_to_date_composite_is_left_alone(tmp_path, monkeypatch, capsys):
    setup_run(tmp_path, monkeypatch)
    composite.main([])
    capsys.readouterr()

    composite.main([])

    assert "Blended 0 composites · 1 already up to date" in capsys.readouterr().out


def test_changing_the_blend_rebuilds_the_composite(tmp_path, monkeypatch, capsys):
    cfg, _ = setup_run(tmp_path, monkeypatch)
    composite.main([])
    capsys.readouterr()

    cfg["composite"]["bandwidth"] = 2.5
    composite.main([])

    assert "Blended 1 composites" in capsys.readouterr().out
    assert read_index(tmp_path)[KEY]["recipe"]["bandwidth"] == 2.5


def test_replacing_an_image_rebuilds_the_composite(tmp_path, monkeypatch, capsys):
    _, folder = setup_run(tmp_path, monkeypatch)
    composite.main([])
    capsys.readouterr()

    noisy(folder / "0002.png", seed=99)  # same file count, different picture
    composite.main([])

    assert "Blended 1 composites" in capsys.readouterr().out


def test_prompts_without_enough_images_are_skipped(tmp_path, monkeypatch, capsys):
    setup_run(tmp_path, monkeypatch, colours=1)

    composite.main([])

    assert "1 prompts skipped" in capsys.readouterr().out
    assert read_index(tmp_path) == {}
