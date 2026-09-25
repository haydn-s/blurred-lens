import numpy as np

from blurred_lens.blend import alpha_blend, blend_typical, effective_count, typicality_weights


def solid(value, size=(64, 64)):
    return np.full((*size, 3), value, dtype=np.uint8)


def test_equal_alphas_are_the_plain_average():
    assert np.abs(alpha_blend([solid(0), solid(30), solid(240)]).astype(int) - 90).max() <= 1


def test_alphas_move_the_blend():
    assert np.abs(alpha_blend([solid(0), solid(200)], [0.25, 0.75]).astype(int) - 150).max() <= 1


def test_an_outlier_keeps_almost_no_weight():
    images = [solid(100 + i) for i in range(9)] + [solid(255)]

    weights = typicality_weights(images)
    blended, _ = blend_typical(images)

    assert weights[-1] < weights[:9].min() / 10
    assert blended.mean() < 110  # the literal average of these is ~119


def test_identical_images_blend_to_themselves():
    images = [solid(120)] * 4
    blended, weights = blend_typical(images)
    assert np.abs(blended.astype(int) - 120).max() <= 1
    assert np.allclose(weights, 0.25)


def test_effective_count_counts_what_the_blend_leant_on():
    assert effective_count([0.5, 0.5]) == 2.0
    assert effective_count([1.0, 0.0]) == 1.0
    assert round(effective_count([0.9, 0.1]), 2) == 1.22
