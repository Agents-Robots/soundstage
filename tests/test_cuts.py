"""Retarded-time solver accuracy, camera cuts and source teleports (FR-42, FR-49)."""

import numpy as np
import pytest

from soundstage.engine import render
from soundstage.engine.control import ControlGrid
from soundstage.engine.geometry import SceneGeometry

from conftest import RATE, frequency, listener_at, rms_db

PLAIN = {"panner": "amplitude", "air_absorption": 0.0}


def test_retarded_delay_is_exact_for_fast_motion(make_scene, sine):
    c, v = 343.0, 0.5 * 343.0  # Mach 0.5, passing 20 m in front
    frames = np.arange(1, 92, dtype=float)
    t = (frames - 1) / 30
    pos = np.stack([-150 + v * t, np.full_like(t, 20.0), np.zeros_like(t)], axis=1)[:, None, :]
    scene = make_scene([{"sample": sine}], pos, frame_end=90, substeps=1)
    grid = ControlGrid.covering(scene.sample_of(31), scene.sample_of(61), RATE)
    path = SceneGeometry(scene, grid).path(0)
    # |s0 + v (t - tau)| = c tau with s0 = (-150, 20): quadratic in tau
    tt = grid.times
    a = v * v - c * c
    b = -2 * v * (-150 + v * tt)
    cc = (-150 + v * tt) ** 2 + 20.0 ** 2
    exact = (-b - np.sqrt(b * b - 4 * a * cc)) / (2 * a)
    assert np.abs(path.tau - exact).max() < 1e-7 and path.audible.all()


def _cut_scene(make_scene, sine, far):
    frames = np.arange(1, 62, dtype=float)
    cam = np.zeros((len(frames), 3))
    cam[frames >= 31, 1] = -95.0  # second camera 100 m from the source
    return make_scene([{"sample": sine}], [[0, 5, 0]], settings=PLAIN, listener=listener_at(cam), cuts=(31,))


def _no_steps(y, amplitude):
    return np.abs(np.diff(y)).max() <= 2 * np.pi * 1000 / RATE * amplitude * 1.5


def test_camera_cut_switches_cleanly(make_scene, sine):
    out = render.render(_cut_scene(make_scene, sine, far=True)).audio[:, 0]
    cut = RATE  # frame 31 = 1.000 s
    near, far = out[cut - RATE // 2: cut - 2000], out[cut + 600: cut + RATE // 2]
    assert rms_db(far) - rms_db(near) == pytest.approx(20 * np.log10(1 / 100) - 20 * np.log10(1 / 5), abs=0.3)
    assert frequency(out[cut + 600: cut + 3000]) == pytest.approx(1000, rel=0.002)  # no glide after the cut
    assert _no_steps(out[cut - 2000: cut + 2000], np.abs(near).max())


def test_source_teleport_away_leaves_a_gap_then_fades_in(make_scene, sine):
    frames = np.arange(1, 62, dtype=float)
    pos = np.zeros((len(frames), 3))
    pos[:, 1] = np.where(frames >= 31, 100.0, 5.0)
    result = render.render(make_scene([{"sample": sine}], pos[:, None, :], settings=PLAIN))
    assert not any("clamped" in w for w in result.warnings)  # the inaudible gap is not near-supersonic motion
    out = result.audio[:, 0]
    t_end_old, t_new = 1.0 + 5 / 343, 1.0 + 100 / 343  # last old sound arrives, first new sound arrives
    gap = out[int((t_end_old + 0.015) * RATE): int((t_new - 0.005) * RATE)]
    after = out[int((t_new + 0.015) * RATE): int((t_new + 0.3) * RATE)]
    assert np.abs(gap).max() < 1e-6
    assert rms_db(after) == pytest.approx(rms_db(0.5 * np.sin(np.arange(RATE) / 7.6)) - 3.01 - 40.0, abs=0.3)
    assert frequency(after) == pytest.approx(1000, rel=0.002)
    region = out[int((t_end_old - 0.05) * RATE): int((t_new + 0.05) * RATE)]
    assert _no_steps(region, np.abs(region).max())


def test_source_teleport_towards_the_camera_switches_with_a_crossfade(make_scene, sine):
    frames = np.arange(1, 62, dtype=float)
    pos = np.zeros((len(frames), 3))
    pos[:, 1] = np.where(frames >= 31, 5.0, 100.0)
    out = render.render(make_scene([{"sample": sine}], pos[:, None, :], settings=PLAIN)).audio[:, 0]
    region = out[int(0.9 * RATE): int(1.3 * RATE)]
    assert _no_steps(region, np.abs(region).max())
    assert frequency(out[int(1.1 * RATE): int(1.3 * RATE)]) == pytest.approx(1000, rel=0.002)


def test_no_pitch_overshoot_where_motion_starts(make_scene, sine):
    frames = 1 + np.arange(4 * 60 + 1) / 4
    x = np.where(frames < 31, -60.0, -60.0 + 30.0 * (frames - 31) / 30)  # stands still, then 30 m/s
    pos = np.stack([x, np.full_like(x, 5.0), np.zeros_like(x)], axis=1)[:, None, :]
    rate = render.render(make_scene([{"sample": sine}], pos, settings=PLAIN, substeps=4)).sources[0]["rate"]
    steady = 343.0 / (343.0 - 30.0 * 60 / np.hypot(60, 5))
    assert rate[1] <= steady * 1.002, (rate, steady)  # a cubic spline overshoots here by about 2 %
