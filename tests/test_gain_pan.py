"""Distance gain, pan laws, camera space, control-rate interpolation and tracks."""

import numpy as np
import pytest

from soundstage.engine import filters, geometry, panning
from soundstage.engine.control import ControlGrid


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


def test_control_interpolation_never_crosses_a_jump():
    grid = ControlGrid(start=0, count=5, rate=48000)
    v = np.array([0.0, 0.0, 0.0, 10.0, 10.0])
    lin = grid.linear(v, 0, 4 * 48, jumps=[3])
    cub = grid.cubic(v, 0, 4 * 48, jumps=[3])
    assert np.all(lin[: 2 * 48] == 0.0) and np.all(lin[2 * 48: 3 * 48] == 10.0)  # step before the jump: new value
    assert np.allclose(cub[: 2 * 48], 0.0) and np.all(cub[2 * 48:] == 10.0)
    smooth = grid.cubic(np.arange(5.0) ** 2, 48, 3 * 48)
    assert np.allclose(smooth, (np.arange(48, 3 * 48) / 48) ** 2, atol=0.13)


def test_track_is_piecewise_and_held_at_piece_ends():
    t = np.arange(6.0)
    pos = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0], [100, 0, 0], [101, 0, 0], [102, 0, 0]], dtype=float)
    starts = geometry.piece_starts(t, pos, max_speed=50.0)
    assert list(starts) == [0, 3]
    track = geometry.Track(t, pos, starts)
    x = track(np.array([1.5, 2.5, 2.99, 3.0, 4.5]))[:, 0]
    assert np.allclose(x, [1.5, 2.0, 2.0, 100.0, 101.5])  # no spline across the teleport


def test_pan_laws_are_constant_power():
    lat = np.linspace(-1, 1, 101)
    for law in panning.PAN_LAWS.values():
        gl, gr = law(lat)
        assert np.allclose(gl ** 2 + gr ** 2, 1.0) and gl[50] == pytest.approx(np.sqrt(0.5))
    gl, gr = panning.power_law(np.array([np.sin(np.radians(76))]))
    assert filters.gain_to_db(gl / gr)[0] == pytest.approx(-18.0, abs=0.5)  # Blender's measured law (#7)


def test_track_reproduces_constant_velocity_and_acceleration_exactly():
    t = np.arange(0, 2.0, 1 / 120)
    for x in (3.0 * t, 1.5 * t ** 2 - 2.0 * t):
        pos = np.stack([x, np.zeros_like(x), np.zeros_like(x)], axis=1)
        track = geometry.Track(t, pos, np.array([0]))
        tt = np.linspace(0.1, 1.8, 777)
        exact = 3.0 * tt if x[1] > 0 else 1.5 * tt ** 2 - 2.0 * tt
        assert np.allclose(track(tt)[:, 0], exact, atol=1e-9)


def test_kinks_split_interpolation_but_smooth_fast_curves_do_not():
    t = np.arange(0, 2.0, 1 / 120)
    start_stop = np.where(t < 1.0, 0.0, 30.0 * (t - 1.0))  # stands still, then 30 m/s
    assert list(geometry.kinks(t, np.stack([start_stop, 0 * t, 0 * t], axis=1))) == [120]
    w = np.sqrt(88.0 / 36.0)  # 9 g circle of radius 36 m (56 m/s)
    circle = np.stack([36 * np.cos(w * t), 36 * np.sin(w * t), 0 * t], axis=1)
    assert len(geometry.kinks(t, circle)) == 0
