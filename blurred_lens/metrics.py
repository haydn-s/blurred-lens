"""Measure one image the way a colorist would describe it.

Every number here exists to be compared across countries: the same measurement on "a city in
Norway" and "a city in Nigeria" is what makes a claim about grading testable. The vocabulary
follows how the yellow "Mexico filter" and its relatives are described in film -- a cast laid over
the frame, warmth in kelvin, saturation, how dark and contrasty the picture is, how hazy the air
looks, and how much of the frame is amber against how much is blue.

No single image can prove a grade was applied: a sunset really in frame is warm content, and from
one picture it looks much like a warm filter. Two things stand in for that separation. The cast is
estimated with a fixed rule that cannot adapt to the picture (an earlier version picked "the least
colorful pixels", which simply followed the grade and reported it backwards), and it is measured
in several parts of the frame at once -- whole image, mid-tones, sky, shadows, highlights. A grade
laid over everything moves all of them together; a golden sky moves mostly the sky.
"""

import cv2
import numpy as np

MINKOWSKI_NORM = 6        # shades-of-gray exponent: 1 is gray-world, higher leans on bright pixels
MIDGRAY = 160.0           # the cast estimate is rendered at this gray, so a*/b* stay comparable
MIDTONE_RANGE = (40.0, 80.0)  # L* band standing in for concrete, walls and road surface
DARK_CHANNEL_PATCH = 15   # window for the dark channel prior, the standard haze statistic
SKY_FRACTION = 0.15       # the top of the frame, where a graded sky shows first

# Hue bands in degrees. Amber covers gold, sand and dust; cool covers cyan through blue.
AMBER_HUES = (20.0, 70.0)
GREEN_HUES = (70.0, 160.0)
COOL_HUES = (180.0, 260.0)


def lab(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """L* (0..100), a* and b* (about -128..127) from an 8-bit RGB image."""
    planes = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    return planes[..., 0] * (100.0 / 255.0), planes[..., 1] - 128.0, planes[..., 2] - 128.0


def lab_of_color(rgb: np.ndarray) -> tuple[float, float, float]:
    """L*, a* and b* of a single color, in floating point.

    Rounding through 8 bits would quantise the cast estimate to whole units, which is coarse next
    to the differences between one country and another.
    """
    patch = (np.asarray(rgb, dtype=np.float32) / 255.0).reshape(1, 1, 3)
    values = cv2.cvtColor(patch, cv2.COLOR_RGB2LAB)[0, 0]
    return float(values[0]), float(values[1]), float(values[2])


def illuminant(rgb: np.ndarray, norm: int = MINKOWSKI_NORM) -> np.ndarray:
    """Shades-of-gray estimate (Finlayson and Trezzi, 2004) of the cast lying over the picture.

    Averaging every pixel (norm 1) is gray-world, which one big green field or blue sky drags
    around; the 6-norm leans on the brighter pixels and is the usual robust compromise. The
    estimate is rescaled to a mid gray, so a picture with no cast comes back neutral and the a*/b*
    of the result describe the cast's direction rather than the scene's brightness.
    """
    channels = rgb.reshape(-1, 3).astype(np.float64) / 255.0
    estimate = np.mean(channels**norm, axis=0) ** (1.0 / norm)
    average = float(estimate.mean())
    if average <= 0:
        return np.full(3, MIDGRAY)
    return np.clip(estimate * (MIDGRAY / average), 0, 255)


def correlated_color_temperature(rgb: np.ndarray) -> float:
    """McCamy's approximation, in kelvin. Lower is warmer (orange), higher is cooler (blue).

    Only meaningful near the Planckian locus, so read it as "how warm this looks" rather than as a
    physical measurement of the light in the scene.
    """
    v = np.asarray(rgb, dtype=np.float64) / 255.0
    linear = np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)
    x, y, z = np.array([[0.4124564, 0.3575761, 0.1804375],
                        [0.2126729, 0.7151522, 0.0721750],
                        [0.0193339, 0.1191920, 0.9503041]]) @ linear
    total = x + y + z
    if total <= 0:
        return float("nan")
    cx, cy = x / total, y / total
    if abs(0.1858 - cy) < 1e-9:
        return float("nan")
    n = (cx - 0.3320) / (0.1858 - cy)
    return float(449 * n**3 + 3525 * n**2 + 6823.3 * n + 5520.33)


def colorfulness(rgb: np.ndarray) -> float:
    """Hasler and Suesstrunk's colorfulness metric (2003): one number for how vivid a picture looks."""
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    rg, yb = r - g, 0.5 * (r + g) - b
    return float(np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean()))


def haze(rgb: np.ndarray, patch: int = DARK_CHANNEL_PATCH) -> float:
    """Dark channel prior (He, Sun and Tang, 2009): high where the air looks dusty or smoggy.

    In a clear picture almost every small patch holds something dark; haze lifts that floor
    everywhere at once.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (patch, patch))
    return float(cv2.erode(rgb.min(axis=2), kernel).mean() / 255.0)


def hue_shares(rgb: np.ndarray, min_saturation: float = 0.2, min_value: float = 0.2) -> dict[str, float]:
    """The share of the frame that is convincingly amber, green or cool."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hue = hsv[..., 0].astype(np.float32) * 2.0  # OpenCV packs 0..360 degrees into 0..179
    strong = (hsv[..., 1] / 255.0 >= min_saturation) & (hsv[..., 2] / 255.0 >= min_value)
    pixels = rgb.shape[0] * rgb.shape[1]

    def band(low: float, high: float) -> float:
        return float((strong & (hue >= low) & (hue < high)).sum() / pixels)

    return {"amber_share": band(*AMBER_HUES), "green_share": band(*GREEN_HUES),
            "cool_share": band(*COOL_HUES)}


def tone(lightness: np.ndarray, b: np.ndarray) -> dict[str, float]:
    """How dark and contrasty the picture is, and which way its shadows and highlights lean.

    Hollywood's habitual grade pushes shadows cool and highlights warm. A yellow filter warms the
    whole frame instead, so watch shadow_b: warm shadows are the tell that the cast is on the
    picture rather than in the light.
    """
    flat_l, flat_b = lightness.ravel(), b.ravel()
    order = np.argsort(flat_l)
    quarter = max(1, len(order) // 4)
    shadows, highlights = order[:quarter], order[-quarter:]
    return {
        "lightness": float(flat_l.mean()),
        "contrast": float(flat_l.std()),
        "shadow_lightness": float(flat_l[shadows].mean()),
        "highlight_lightness": float(flat_l[highlights].mean()),
        "shadow_b": float(flat_b[shadows].mean()),
        "highlight_b": float(flat_b[highlights].mean()),
    }


def edge_density(rgb: np.ndarray) -> float:
    """How busy the frame is: the share of pixels Canny calls an edge."""
    return float((cv2.Canny(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), 50, 150) > 0).mean())


def measure(rgb: np.ndarray) -> dict[str, float]:
    """Every metric for one 8-bit RGB image, as a flat dict of plain floats."""
    lightness, a, b = lab(rgb)
    cast = illuminant(rgb)
    _, cast_a, cast_b = lab_of_color(cast)
    midtone = (lightness >= MIDTONE_RANGE[0]) & (lightness <= MIDTONE_RANGE[1])
    if not midtone.any():
        midtone = np.ones(lightness.shape, dtype=bool)
    sky_l, sky_a, sky_b = lab(rgb[:max(1, int(round(rgb.shape[0] * SKY_FRACTION)))])

    out = {
        "a": float(a.mean()),
        "b": float(b.mean()),
        "chroma": float(np.hypot(a, b).mean()),
        "colorfulness": colorfulness(rgb),
        "cast_a": cast_a,
        "cast_b": cast_b,
        "cast_kelvin": correlated_color_temperature(cast),
        "midtone_a": float(a[midtone].mean()),
        "midtone_b": float(b[midtone].mean()),
        "haze": haze(rgb),
        "edge_density": edge_density(rgb),
        "sky_lightness": float(sky_l.mean()),
        "sky_a": float(sky_a.mean()),
        "sky_b": float(sky_b.mean()),
    }
    out.update(hue_shares(rgb))
    out.update(tone(lightness, b))
    # Positive is the classic cool-shadow, warm-highlight split; near zero or negative means the
    # whole frame leans one way, which is what a flat filter looks like.
    out["warm_split"] = out["highlight_b"] - out["shadow_b"]
    return out


METRICS = tuple(measure(np.zeros((8, 8, 3), dtype=np.uint8)))
