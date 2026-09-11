import numpy as np
from PIL import Image

from blurred_lens.composite import make_composites


def test_mean_and_median_of_solid_images(tmp_path):
    files = []
    for i, gray in enumerate([0, 30, 240]):
        path = tmp_path / f"{i + 1:04d}.png"
        Image.new("RGB", (64, 32), (gray, gray, gray)).save(path)
        files.append(path)

    out = make_composites(files, width=16)

    assert out["mean"].size == (16, 8)  # aspect ratio kept
    assert np.abs(np.asarray(out["mean"]).astype(int) - 90).max() <= 1
    assert np.abs(np.asarray(out["median"]).astype(int) - 30).max() <= 1
