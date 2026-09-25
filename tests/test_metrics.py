import cv2
import numpy as np

from blurred_lens.metrics import METRICS, colorfulness, haze, measure


def photo(seed=0, size=64):
    """A textured stand-in for a generated photo; a flat image measures as blank, not as a picture."""
    rng = np.random.default_rng(seed)
    small = rng.integers(60, 200, (8, 8, 3), dtype=np.uint8)
    return cv2.resize(small, (size, size), interpolation=cv2.INTER_LINEAR)


def graded(image, gains):
    return np.clip(image * np.array(gains), 0, 255).astype(np.uint8)


def test_a_warm_grade_reads_as_warmer():
    """Guards the bug this replaced: estimating the cast from "the least colorful pixels" made the
    estimate follow the grade, so a warmed picture came back cooler."""
    image = photo()

    warm = measure(graded(image, (1.15, 1.02, 0.80)))
    plain = measure(image)
    cool = measure(graded(image, (0.85, 1.0, 1.18)))

    assert cool["cast_b"] < plain["cast_b"] < warm["cast_b"]
    assert cool["cast_kelvin"] > plain["cast_kelvin"] > warm["cast_kelvin"]
    assert cool["midtone_b"] < plain["midtone_b"] < warm["midtone_b"]
    assert cool["amber_share"] <= plain["amber_share"] <= warm["amber_share"]


def test_a_neutral_picture_has_no_cast():
    gray = np.dstack([np.tile(np.arange(0, 256, 4, dtype=np.uint8), (64, 1))] * 3)

    out = measure(gray)

    assert abs(out["cast_a"]) < 1 and abs(out["cast_b"]) < 1
    assert 6300 < out["cast_kelvin"] < 6700  # sRGB's own white point, near D65
    assert out["colorfulness"] < 1


def test_haze_rises_when_the_blacks_are_lifted():
    image = photo(seed=1)
    dusty = np.clip(image * 0.5 + 110, 0, 255).astype(np.uint8)

    assert haze(dusty) > haze(image)


def test_colorfulness_puts_gray_below_color():
    assert colorfulness(np.full((32, 32, 3), 128, np.uint8)) < colorfulness(photo(seed=3))


def test_every_metric_is_a_finite_number():
    out = measure(photo(seed=5))

    assert set(out) == set(METRICS)
    assert all(np.isfinite(value) for value in out.values())
