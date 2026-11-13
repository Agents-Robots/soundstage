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
    gl, gr = panning.sine_law(lat)
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


def _heard_deg(lateral: np.ndarray, law=panning.sine_law) -> np.ndarray:
    """Phantom image angle on loudspeakers at +-30 deg (tangent law) for lateral sines."""
    gl, gr = law(lateral)
    return np.degrees(np.arctan(np.tan(np.radians(30)) * (gr - gl) / (gr + gl)))


def _directions(azimuth_deg: np.ndarray, distance: float = 50.0) -> np.ndarray:
    a = np.radians(azimuth_deg)
    return np.stack([distance * np.sin(a), np.zeros_like(a), -distance * np.cos(a)], axis=1)


@pytest.mark.parametrize("law", [panning.sine_law, panning.power_law])
@pytest.mark.parametrize("focal_mm", [24.0, 50.0, 200.0])
def test_screen_panning_places_the_frame_on_the_screen(law, focal_mm):
    half = 18.0 / focal_mm  # 36 mm sensor
    edge = np.degrees(np.arctan(half))
    quarter = np.degrees(np.arctan(half / 2))
    az = np.array([0.0, quarter, edge, -edge])
    n = len(az)
    lat = panning.screen_lateral(_directions(az), np.full(n, -half), np.full(n, half), 16.5, law, geometry.R_MIN)
    heard = _heard_deg(lat, law)
    target = np.degrees(np.arctan(np.array([0.0, 0.5, 1.0, -1.0]) * np.tan(np.radians(16.5))))
    assert heard == pytest.approx(target, abs=0.05)


def test_screen_panning_follows_lens_shift():
    # frame shifted right: its centre is heard in the middle, a source straight ahead to the left
    lat = panning.screen_lateral(_directions(np.array([np.degrees(np.arctan(0.25)), 0.0])), np.full(2, -0.25),
                                 np.full(2, 0.75), 16.5, panning.sine_law, geometry.R_MIN)
    assert lat[0] == pytest.approx(0.0, abs=1e-3) and lat[1] < -0.1


def test_screen_panning_is_continuous_and_keeps_the_back():
    az = np.linspace(-179.0, 179.0, 3581)
    n = len(az)
    q = _directions(az)
    lat = panning.screen_lateral(q, np.full(n, -0.36), np.full(n, 0.36), 16.5, panning.sine_law, geometry.R_MIN)
    assert np.abs(np.diff(lat)).max() < 0.01
    ahead = np.abs(az) <= 90
    assert np.all(np.diff(lat[ahead]) > 0)  # monotonic across the front
    behind = np.abs(az) > 90
    assert lat[behind] == pytest.approx(geometry.derived(q)["lateral"][behind])


def test_screen_panning_without_a_frame_follows_the_camera():
    q = _directions(np.array([-60.0, 10.0, 45.0]))
    lat = panning.screen_lateral(q, np.full(3, np.nan), np.full(3, np.nan), 16.5, panning.sine_law, geometry.R_MIN)
    assert lat == pytest.approx(geometry.derived(q)["lateral"])


def _hybrid(**settings) -> panning.HybridPanner:
    return panning.HybridPanner({"pan_law": "sine", "ild_limit_db": 12.0, "screen_edge_deg": 16.5, **settings})


def test_hybrid_limits_the_level_difference_at_the_side():
    p = _hybrid()
    gl, gr = p.pan_gains(np.array([-1.0, 1.0]))
    assert filters.gain_to_db(gr / gl) == pytest.approx([-12.0, 12.0], abs=0.01)
    assert np.allclose(gl ** 2 + gr ** 2, 1.0)


def test_hybrid_limit_keeps_the_frame_and_is_monotonic():
    p = _hybrid()
    lat = np.linspace(-1, 1, 2001)
    gl, gr = p.pan_gains(lat)
    ratio = (gr - gl) / (gr + gl)
    assert np.all(np.diff(ratio) > 0)
    inside = np.abs(lat) <= p.knee
    assert _heard_deg(lat[inside], p.pan_gains) == pytest.approx(_heard_deg(lat[inside], panning.sine_law))
    assert _heard_deg(np.array([p.knee]), p.pan_gains)[0] == pytest.approx(16.5, abs=0.05)  # the frame edge


def test_hybrid_limit_below_the_frame_edge_scales_and_none_turns_it_off():
    gl, gr = _hybrid(ild_limit_db=6.0).pan_gains(np.array([0.0, 0.5, 1.0]))
    db = filters.gain_to_db(gr / gl)
    assert db[0] == pytest.approx(0.0) and 0 < db[1] < db[2] and db[2] == pytest.approx(6.0, abs=0.01)
    lat = np.linspace(-0.99, 0.99, 11)
    assert np.allclose(_hybrid(ild_limit_db=None).pan_gains(lat), panning.sine_law(lat))
