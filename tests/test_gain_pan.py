"""Distance gain and panning. Cones and rear cue follow in Phase 2."""

import numpy as np
import pytest

from soundstage.engine import filters, geometry, panning


def test_inverse_clamped_halves_per_doubling():
    g = filters.distance_gain(np.array([0.5, 1.0, 2.0, 4.0]), "inverse_clamped", 1.0, None, 1.0)
    assert np.allclose(g, [1.0, 1.0, 0.5, 0.25])
    assert filters.gain_to_db(g[2]) == pytest.approx(-6.02, abs=0.01)


def test_max_distance_clamps_inverse_and_zeroes_linear():
    assert filters.distance_gain(np.array([100.0]), "inverse_clamped", 1.0, 10.0, 1.0)[0] == pytest.approx(0.1)
    g = filters.distance_gain(np.array([1.0, 5.5, 10.0, 20.0]), "linear_clamped", 1.0, 10.0, 1.0)
    assert np.allclose(g, [1.0, 0.5, 0.0, 0.0])


def test_exponential_and_none():
    assert filters.distance_gain(np.array([4.0]), "exponential_clamped", 1.0, None, 2.0)[0] == pytest.approx(1 / 16)
    assert filters.distance_gain(np.array([1e6]), "none", 1.0, None, 1.0)[0] == 1.0


def test_constant_power_pan():
    lat = np.linspace(-1, 1, 101)
    gl, gr = panning.constant_power(lat)
    assert np.allclose(gl ** 2 + gr ** 2, 1.0)
    assert gl[0] == pytest.approx(1.0) and gr[-1] == pytest.approx(1.0)
    assert gl[50] == pytest.approx(gr[50]) == pytest.approx(np.sqrt(0.5))


def test_camera_space_convention():
    # Camera at the origin looking along +Y: world +X is right (+x), world +Y is in front (-z).
    m = np.eye(4)
    m[:3, :3] = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]
    q = geometry.camera_space(m[None], np.array([[[5.0, 0, 0], [0, 7.0, 0], [0, 0, 3.0]]]))[0]
    assert np.allclose(q, [[5, 0, 0], [0, 0, -7], [0, 3, 0]])


def test_source_through_camera_pans_smoothly():
    x = np.linspace(-2, 2, 4001)
    q = np.stack([x, np.zeros_like(x), np.zeros_like(x)], axis=1)
    lat = geometry.derived(q)["lateral"]
    assert np.abs(np.diff(lat)).max() < 0.01


def test_interpolation_steps_at_cuts():
    t = np.array([0.0, 1.0, 2.0])
    v = np.array([[0.0], [0.0], [10.0]])
    out = geometry.interpolate(t, v, np.array([0.5, 1.5, 1.999]), cut_times=np.array([2.0]))
    assert np.allclose(out[:, 0], [0.0, 0.0, 0.0])
