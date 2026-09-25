"""Blend one prompt's images into a single composite with OpenCV alpha blending.

Laying every image over the last with the same alpha just rebuilds the literal average, which
mixes a model's rare answers into its common ones in equal measure. Here each image gets an alpha
from how typical it is: a mean-shift search walks to the densest cluster of responses, and images
near that cluster are composited at full strength while outliers fade out. The result is the
picture the model tends to draw, not the arithmetic middle of everything it drew.

`composite.bandwidth` in config.toml sets how tight that focus is. Small values put nearly all the
alpha on the most typical image; large values spread it out and approach the flat average.
"""

from collections.abc import Sequence

import cv2
import numpy as np

THUMB = 32  # images are compared as 32x32 thumbnails: coarse layout and colour, not fine detail


def descriptors(images: Sequence[np.ndarray]) -> np.ndarray:
    """Each image as one vector, so "typical" means typical layout and colour."""
    small = [cv2.resize(img, (THUMB, THUMB), interpolation=cv2.INTER_AREA) for img in images]
    return np.asarray(small, dtype=np.float32).reshape(len(small), -1) / 255.0


def typicality_weights(images: Sequence[np.ndarray], bandwidth: float = 1.0, iterations: int = 5) -> np.ndarray:
    """How much each image should count in the blend; the weights add up to 1.

    Starts from equal weights, then repeatedly moves a reference point to the weighted centre of
    the images and re-weights each image by a Gaussian of its distance from it. That walk climbs
    towards the densest group of responses, so a lone night shot among daytime streets keeps very
    little weight while the crowd around the centre keeps most of it.
    """
    points = descriptors(images)
    weights = np.full(len(points), 1.0 / len(points))
    for _ in range(max(1, iterations)):
        centre = weights @ points
        distance = np.linalg.norm(points - centre, axis=1)
        scale = bandwidth * float(np.median(distance))
        if scale <= 0:  # one image, or every image identical: nothing to tell apart
            break
        weights = np.exp(-0.5 * (distance / scale) ** 2)
        weights /= weights.sum()  # at least half the images sit within one bandwidth, so this is > 0
    return weights


def alpha_blend(images: Sequence[np.ndarray], weights: Sequence[float] | None = None) -> np.ndarray:
    """Blend images into one by alpha compositing them in turn with cv2.addWeighted.

    Each image goes over the running result with alpha = its weight / the weight carried so far,
    the classic way to fold a stack of photographs into one exposure. The least typical images are
    laid down first and the most typical last. Equal weights give the plain average.
    """
    if len(images) == 0:
        raise ValueError("nothing to blend")
    weights = np.full(len(images), 1.0) if weights is None else np.asarray(weights, dtype=np.float64)
    if weights.shape != (len(images),):
        raise ValueError(f"got {weights.shape[0]} weights for {len(images)} images")
    total = float(weights.sum())
    if total <= 0:
        raise ValueError("the weights add up to nothing")
    weights = weights / total

    blended = np.zeros(np.shape(images[0]), dtype=np.float32)
    carried = 0.0
    for i in np.argsort(weights):
        if weights[i] <= 0:
            continue
        carried += float(weights[i])
        alpha = float(weights[i]) / carried
        blended = cv2.addWeighted(blended, 1.0 - alpha, images[i].astype(np.float32), alpha, 0.0)
    return blended.round().clip(0, 255).astype(np.uint8)


def blend_typical(images: Sequence[np.ndarray], bandwidth: float = 1.0,
                  iterations: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """The composite for one prompt, and the weights it was built from."""
    weights = typicality_weights(images, bandwidth, iterations)
    return alpha_blend(images, weights), weights


def effective_count(weights: Sequence[float]) -> float:
    """How many images the blend really leant on: 1/sum(w^2), so all the weight on one image is 1.

    Worth recording next to the raw count: 1,000 images with an effective count of 30 means the
    model kept answering in one narrow way, and the rest barely touched the picture.
    """
    w = np.asarray(weights, dtype=np.float64)
    if w.size == 0:
        return 0.0
    w = w / w.sum()
    return float(1.0 / np.sum(w**2))
