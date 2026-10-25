"""Delay, Doppler, ITD, rate clamp, pre-roll and chunking (Phase 2 known answers)."""

import numpy as np
import pytest
from scipy.signal import correlate, resample_poly

from soundstage.engine import render

from conftest import RATE, frequency, listener_at, peak_index, rms_db

PLAIN = {"panner": "amplitude", "air_absorption": 0.0}
C, V = 343.0, 34.3


def _flyby(make_scene, sample, *, moving="source", settings=None):
    """Source (or camera) moving along x at 34.3 m/s, passing 3 m from the other at t = 6.4 s."""
    frames = np.arange(1, 392, dtype=float)
    x = -220.0 + V * (frames - 1) / 30
    line = np.stack([x, np.zeros_like(x), np.zeros_like(x)], axis=1)
    s = {**PLAIN, **(settings or {})}
    if moving == "source":
        return make_scene([{"sample": sample}], (line + [0, 3, 0])[:, None, :], frame_end=390, settings=s)
    return make_scene([{"sample": sample}], [[0, 3, 0]], frame_end=390, settings=s, listener=listener_at(line))


def _approach_recede(out):
    mono = out.sum(axis=1)
    return frequency(mono[int(2.0 * RATE): int(2.5 * RATE)]), frequency(mono[int(11.5 * RATE): int(12.0 * RATE)])


def test_moving_source_doppler(make_scene, sine):
    up, down = _approach_recede(render.render(_flyby(make_scene, sine)).audio)
    assert up == pytest.approx(1000 * C / (C - V), rel=0.005)  # 1111 Hz
    assert down == pytest.approx(1000 * C / (C + V), rel=0.005)  # 909 Hz


def test_moving_camera_doppler(make_scene, sine):
    up, down = _approach_recede(render.render(_flyby(make_scene, sine, moving="camera")).audio)
    assert up == pytest.approx(1000 * (C + V) / C, rel=0.005)  # 1100 Hz
    assert down == pytest.approx(1000 * (C - V) / C, rel=0.005)  # 900 Hz


@pytest.mark.parametrize("k", [0.0, 2.0])
def test_doppler_factor_scales_the_shift(make_scene, sine, k):
    up, down = _approach_recede(render.render(_flyby(make_scene, sine, settings={"doppler_factor": k})).audio)
    assert up == pytest.approx(1000 * (1 + k * V / (C - V)), rel=0.005)
    assert down == pytest.approx(1000 * (1 - k * V / (C + V)), rel=0.005)


def test_source_at_343_m_is_heard_one_second_late(make_scene, click):
    scene = make_scene([{"sample": click, "mode": "once", "frame": 10}], [[0, 343, 0]], frame_end=90, settings=PLAIN)
    assert abs(peak_index(render.render(scene).audio) - (9 * 1600 + RATE)) <= 1


def test_sync_to_picture_puts_the_onset_on_its_frame(make_scene, click):
    scene = make_scene([{"sample": click, "mode": "once", "frame": [10, 40], "sync_to_picture": True}],
                       [[0, 343, 0]], frame_end=90, settings=PLAIN)
    out = render.render(scene).audio
    assert peak_index(out[: 30 * 1600]) == 9 * 1600 and peak_index(out[30 * 1600:]) + 30 * 1600 == 39 * 1600


@pytest.mark.parametrize("itd_scale", [1.0, 0.5])
def test_itd_at_90_degrees(make_scene, wav, itd_scale):
    noise = wav("noise.wav", np.random.default_rng(3).standard_normal(RATE // 4) * 0.3)
    s = {"panner": "hybrid", "head_shadow": 0.0, "itd_scale": itd_scale, "air_absorption": 0.0, "rear_gain_db": 0.0}
    out = render.render(make_scene([{"sample": noise, "mode": "once", "frame": 5}], [[100, 0, 0]], settings=s)).audio
    left, right = (resample_poly(out[:, i], 4, 1) for i in (0, 1))
    lag = np.argmax(correlate(left, right, mode="full")) - (len(right) - 1)  # left lags right
    assert lag == pytest.approx(0.656e-3 * itd_scale * 4 * RATE, abs=1.0)


def test_supersonic_approach_is_clamped_and_reported(make_scene, sine):
    frames = np.arange(1, 62, dtype=float)
    pos = np.stack([np.zeros_like(frames), 300 - 330 * (frames - 1) / 30, np.zeros_like(frames)], axis=1)
    result = render.render(make_scene([{"sample": sine}], pos[:, None, :], settings=PLAIN))
    assert np.isfinite(result.audio).all()
    assert result.sources[0]["rate"][1] == pytest.approx(4.0)
    assert any("playback rate clamped" in w for w in result.warnings)


def test_loop_running_before_the_shot_is_heard_from_the_first_sample(make_scene, sine):
    out = render.render(make_scene([{"sample": sine}], [[0, 343, 0]], frame_end=90, settings=PLAIN)).audio
    assert rms_db(out[: RATE // 10]) == pytest.approx(rms_db(out[RATE: RATE + RATE // 10]), abs=0.2)


def test_threads_do_not_change_the_output_and_chunks_only_round(make_scene, sine, monkeypatch):
    scene = _flyby(make_scene, sine, settings={"panner": "hybrid", "air_absorption": 1.0})
    reference = render.render(scene, workers=1).audio
    assert np.array_equal(render.render(scene, workers=8).audio, reference)  # bit-identical (NFR-2)
    monkeypatch.setattr(render, "CHUNK_BLOCKS", 377)  # other window alignment: float rounding only
    assert np.abs(render.render(scene, workers=4).audio - reference).max() < 1e-12


def test_report_has_delay_and_rate(make_scene, sine):
    st = render.render(_flyby(make_scene, sine)).sources[0]
    assert st["rate"][0] == pytest.approx(C / (C + V), abs=0.01) and st["rate"][1] == pytest.approx(C / (C - V), abs=0.01)
    assert st["delay_ms"][0] == pytest.approx(3 / C * 1000, abs=1.0)
