"""Air absorption, head shadow, rear cue, cone, and smoothness when a source passes the camera."""

import numpy as np
import pytest
from scipy.signal import csd, welch

from soundstage.engine import filters, render
from soundstage.engine.control import ControlGrid

from conftest import RATE

# ISO 9613-2 Table 2, dB/km at 63 Hz ... 8 kHz (octave bands)
ISO_TABLE_2 = {
    (10, 70): [0.1, 0.4, 1.0, 1.9, 3.7, 9.7, 32.8, 117],
    (20, 70): [0.1, 0.3, 1.1, 2.8, 5.0, 9.0, 22.9, 76.6],
    (30, 70): [0.1, 0.3, 1.0, 3.1, 7.4, 12.7, 23.1, 59.3],
    (15, 20): [0.3, 0.6, 1.2, 2.7, 8.2, 28.2, 88.8, 202],
    (15, 50): [0.1, 0.5, 1.2, 2.2, 4.2, 10.8, 36.2, 129],
    (15, 80): [0.1, 0.3, 1.1, 2.4, 4.1, 8.3, 23.7, 82.8],
}


@pytest.mark.parametrize("conditions", ISO_TABLE_2)
def test_iso9613_matches_table_2(conditions):
    centres = 1000 * 10 ** (np.arange(-12, 10, 3) / 10)  # exact band centres 63.1 ... 7943 Hz
    got = filters.iso9613_alpha(centres, *conditions) * 1000
    ref = np.array(ISO_TABLE_2[conditions])
    assert np.all(np.abs(got - ref) <= np.maximum(0.06, 0.005 * ref)), got  # the table's rounding


def _transfer_db(a, b, f):
    """|H| in dB from signal a to signal b at frequencies f (same excitation in both)."""
    fr, pxy = csd(a, b, fs=RATE, nperseg=4096)
    _, pxx = welch(a, fs=RATE, nperseg=4096)
    return np.interp(f, fr, 20 * np.log10(np.abs(pxy / pxx)))


@pytest.mark.parametrize("distance", [10.0, 100.0, 1000.0])
def test_air_absorption_follows_iso9613_in_a_render(make_scene, wav, distance):
    noise = wav("noise.wav", np.random.default_rng(5).standard_normal(RATE * 2) * 0.1)
    base = {"panner": "amplitude", "doppler_factor": 0.0}
    dry, wet = (render.render(make_scene([{"sample": noise}], [[0, distance, 0]], frame_end=150,
                                         settings={**base, "air_absorption": a})).audio[RATE * 4:, 0] for a in (0.0, 1.0))
    f = np.array([1000.0, 4000.0, 8000.0, 16000.0])
    loss = -_transfer_db(dry, wet, f)
    iso = filters.iso9613_alpha(f) * distance
    designed = filters._onepole_loss_db(f, filters.AirAbsorption(20, 50, 2 * RATE).cutoffs(np.array([distance]))[0],
                                        2 * RATE)
    audible = iso < 20
    assert np.all(np.abs(loss - designed)[audible] < 0.5), (loss, designed)  # the render realizes the design
    assert np.all(np.abs(loss - iso)[audible] < 2.6), (loss, iso)  # the design follows ISO 9613-1
    assert np.all(loss[~audible] > 17.0)


def test_air_absorption_off_and_bypass_for_near_sources():
    air = filters.AirAbsorption(20, 50, 96000, scale=0.0)
    assert np.all(np.isinf(air.cutoffs(np.array([10.0, 1000.0]))))
    assert np.all(np.isinf(filters.AirAbsorption(20, 50, 96000).cutoffs(np.array([0.1]))))


def _shelf_response_db(alpha, f, rate=RATE):
    b0, b1, a1 = filters.head_shadow_coefficients(np.full(1, alpha), 0.0875, 343.0, rate)
    z = np.exp(-2j * np.pi * f / rate)
    return 20 * np.log10(np.abs((b0 + b1 * z) / (1 + a1 * z)))


def test_head_shadow_matches_brown_duda():
    wp = 2 * 343.0 / 0.0875
    f = np.array([100.0, 500.0, 1000.0, 2000.0, 4000.0])
    for theta, expected_alpha in ((0.0, 2.0), (150.0, 0.1), (180.0, 1.05 + 0.95 * np.cos(np.radians(216)))):
        alpha = filters.head_shadow_alpha(np.cos(np.radians(np.array([theta]))), 1.0)[0]
        assert alpha == pytest.approx(expected_alpha)
        analog = 20 * np.log10(np.abs((1 + 1j * alpha * 2 * np.pi * f / wp) / (1 + 1j * 2 * np.pi * f / wp)))
        assert np.allclose(_shelf_response_db(alpha, f), analog, atol=0.5)
    assert _shelf_response_db(1.0, np.array([10000.0]))[0] == pytest.approx(0.0, abs=1e-9)  # strength 0: flat
    assert filters.head_shadow_alpha(np.array([-1.0]), 0.0)[0] == 1.0


def test_rear_cue_low_passes_and_attenuates_a_source_behind(make_scene, wav):
    noise = wav("noise.wav", np.random.default_rng(6).standard_normal(RATE * 2) * 0.1)
    s = {"air_absorption": 0.0, "doppler_factor": 0.0, "itd_scale": 0.0, "head_shadow": 0.0}
    front, back = (render.render(make_scene([{"sample": noise, "loop_phase": 0.0}], [p], settings=s)).audio[RATE:, 0]
                   for p in ([0, 10, 0], [0, -10, 0]))
    h = _transfer_db(front, back, np.array([200.0, 6000.0]))
    assert h[0] == pytest.approx(-2.0, abs=0.2)  # rear_gain_db
    assert h[1] == pytest.approx(-2.0 - 3.0, abs=0.6)  # one-pole at rear_cutoff_hz: -3 dB there


def test_cone_law():
    angles = np.radians([0, 45, 67.5, 90, 150])
    g = filters.cone_gain(np.cos(angles), 90.0, 180.0, -12.0)
    g_out = 10 ** (-12 / 20)
    assert np.allclose(g, [1, 1, 1 + 0.5 * (g_out - 1), g_out, g_out])
    assert np.all(filters.cone_gain(np.cos(angles), 360.0, 360.0, -12.0) == 1.0)


def test_emitter_facing_away_is_quieter(make_scene, sine):
    src = {"sample": sine, "cone_inner_deg": 60.0, "cone_outer_deg": 120.0, "cone_outer_gain_db": -12.0}
    plain = {"panner": "amplitude", "air_absorption": 0.0}
    n = 61
    toward, away = (render.render(make_scene([src], [[0, 10, 0]], settings=plain,
                                             src_fwd=np.tile([[[0.0, d, 0.0]]], (n, 1, 1)))).audio for d in (-1.0, 1.0))
    assert 20 * np.log10(np.std(away) / np.std(toward)) == pytest.approx(-12.0, abs=0.1)


def test_source_passing_through_the_camera_has_no_steps(make_scene, sine):
    frames = np.arange(1, 62, dtype=float)
    x = -3.0 + 2.0 * (frames - 1) / 30  # walks through the camera at 2 m/s
    pos = np.stack([x, np.zeros_like(x), np.zeros_like(x)], axis=1)[:, None, :]
    out = render.render(make_scene([{"sample": sine}], pos)).audio
    for ch in (0, 1):
        y = out[RATE // 2: -RATE // 2, ch]
        natural = 2 * np.pi * 1000 / RATE * np.abs(y).max() * 1.02
        assert np.abs(np.diff(y)).max() <= natural * 1.5
        env = np.sqrt((y[: len(y) // 48 * 48].reshape(-1, 48) ** 2).mean(axis=1))
        assert np.abs(np.diff(20 * np.log10(env + 1e-9))).max() < 0.5  # level changes smoothly (1 ms blocks)


def test_one_pole_stage_is_minus_3db_at_its_cutoff():
    stage = filters.OnePoleStage(np.array([0.0, 10.0]), np.array([[2000.0], [2000.0]]), RATE)
    x = np.random.default_rng(1).standard_normal(RATE)
    y = stage.process(x, 0, RATE)
    assert _transfer_db(x, y, np.array([2000.0]))[0] == pytest.approx(-3.01, abs=0.1)


def test_shelf_stage_chunks_equal_one_call():
    grid = ControlGrid(start=0, count=30, rate=RATE)
    alpha = np.linspace(0.2, 2.0, 30)
    b0, b1, a1 = filters.head_shadow_coefficients(alpha, 0.0875, 343.0, RATE)
    x = np.random.default_rng(2).standard_normal(1000)
    whole = filters.ShelfStage(grid, b0, b1, a1).process(x, 0, 1000)
    st = filters.ShelfStage(grid, b0, b1, a1)
    parts = np.concatenate([st.process(x[:400], 0, 400), st.process(x[400:], 400, 1000)])
    assert np.array_equal(parts, whole)
