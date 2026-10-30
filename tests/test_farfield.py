"""Far field (level of detail, FR-56): equivalence with the full chain, known answers, tier switches."""

import numpy as np
import pytest
from scipy.signal import welch

from soundstage.engine import farfield, render
from soundstage.engine.scene import load_scene

from conftest import RATE, frequency, rms_db

PLAIN = {"panner": "amplitude", "air_absorption": 0.0, "cull_db": None}
C, V = 343.0, 34.3


@pytest.fixture
def tiers(monkeypatch):
    """Force the tiers: ``set(fn)`` with fn(source index, chunk index) -> near."""

    def set_tiers(fn):
        def assign(energy, groups, spatial, spans, n_chunks, detail):
            return np.array([[(not sp) or fn(i, c) for c in range(n_chunks)] for i, sp in enumerate(spatial)])
        monkeypatch.setattr(farfield, "assign_tiers", assign)

    return set_tiers


@pytest.fixture
def noise(wav):
    return wav("noise.wav", 0.3 * np.random.default_rng(1).standard_normal(RATE * 2))


def _pair(scene):
    """The same scene rendered with every source near (reference) and every source far."""
    full = render.render(load_scene(scene.path, {"detail_voices": None}))
    lod = render.render(scene)
    return full, lod


def _error_db(ref, x):
    return 10 * np.log10(np.sum((ref - x) ** 2) / np.sum(ref ** 2))


def test_far_source_equals_the_full_chain_without_filters(make_scene, noise, tiers):
    tiers(lambda i, c: False)
    scene = make_scene([{"sample": noise}], [[12.0, 16.0, 1.0]], frame_end=150, settings=PLAIN)
    full, lod = _pair(scene)
    assert lod.lod is not None and lod.lod["far_sources"] == 1
    assert _error_db(full.audio, lod.audio) < -60.0


def test_far_air_absorption_follows_the_band_at_its_distance(make_scene, noise, tiers):
    tiers(lambda i, c: False)
    settings = {**PLAIN, "air_absorption": 1.0}
    scene = make_scene([{"sample": noise}], [[0.0, 400.0, 0.0]], frame_end=150, settings=settings)
    full, lod = _pair(scene)
    a, b = full.audio[RATE * 2:, 0], lod.audio[RATE * 2:, 0]
    f, pa = welch(a, RATE, nperseg=4096)
    _, pb = welch(b, RATE, nperseg=4096)
    band = (f > 100) & (f < 5000)  # loss up to about 20 dB, where the air fits are accurate
    diff = 10 * np.log10(pb[band] / pa[band])
    assert np.abs(diff).max() < 0.5


@pytest.mark.parametrize("distance", [59.5, 84.1])
def test_far_air_absorption_between_bands(make_scene, noise, tiers, distance):
    # halfway (in log distance) between two bands a voice is the sum of their filters, whose phases
    # differ (up to 0.3 dB at 6.5 kHz), and the far field's air fit (48 kHz) differs from the full
    # chain's (96 kHz) by up to 0.3 dB: sqrt(2) apart the tiers stay within 0.8 dB (E05)
    tiers(lambda i, c: False)
    settings = {**PLAIN, "air_absorption": 1.0}
    scene = make_scene([{"sample": noise}], [[0.0, distance, 0.0]], frame_end=150, settings=settings)
    full, lod = _pair(scene)
    a, b = full.audio[RATE * 2:, 0], lod.audio[RATE * 2:, 0]
    f, pa = welch(a, RATE, nperseg=4096)
    _, pb = welch(b, RATE, nperseg=4096)
    band = (f > 100) & (f < 6500)
    diff = 10 * np.log10(pb[band] / pa[band])
    assert np.abs(diff).max() < 0.8


def test_far_field_beside_a_bed(make_scene, noise, tiers):
    # a non-spatial source is always near; its renderer has no distance statistics for the report
    tiers(lambda i, c: False)
    scene = make_scene([{"sample": noise}, {"sample": noise, "spatial": False}], [[0.0, 50.0, 0.0]],
                       frame_end=150, settings=PLAIN)
    out = render.render(scene, stems=True)
    assert np.isfinite(out.audio).all() and rms_db(out.audio[RATE:, 0]) > -40


def test_far_doppler_known_answer(make_scene, sine, tiers):
    tiers(lambda i, c: False)
    frames = np.arange(1, 392, dtype=float)
    x = -220.0 + V * (frames - 1) / 30
    line = np.stack([x, np.full_like(x, 3.0), np.zeros_like(x)], axis=1)
    out = render.render(make_scene([{"sample": sine}], line[:, None, :], frame_end=390, settings=PLAIN)).audio
    mono = out.sum(axis=1)
    assert frequency(mono[int(2.0 * RATE): int(2.5 * RATE)]) == pytest.approx(1000 * C / (C - V), rel=0.005)
    assert frequency(mono[int(11.5 * RATE): int(12.0 * RATE)]) == pytest.approx(1000 * C / (C + V), rel=0.005)


def test_far_delay_and_side(make_scene, click, tiers):
    tiers(lambda i, c: False)
    scene = make_scene([{"sample": click, "mode": "once", "frame": 10}], [[343.0 * 0.6, 343.0 * 0.8, 0]],
                       frame_end=90, settings=PLAIN)
    out = render.render(scene).audio
    assert abs(int(np.argmax(np.abs(out).sum(axis=1))) - (9 * 1600 + RATE)) <= 1  # 343 m: 1.000 s late
    assert rms_db(out[:, 1]) > rms_db(out[:, 0]) + 3  # on the right


def test_tier_switches_are_smooth(make_scene, noise, tiers):
    # near in the second of three chunks: far -> near -> far at 4 s and 8 s
    tiers(lambda i, c: c == 1)
    scene = make_scene([{"sample": noise}], [[10.0, 10.0, 0.0]], frame_end=359, settings=PLAIN)
    out = render.render(scene).audio[:, 0]
    level = [rms_db(out[a - 4800:a + 4800]) for a in (RATE * 2, RATE * 4, RATE * 6, RATE * 8, RATE * 10)]
    assert max(level) - min(level) < 1.0
    step = np.abs(np.diff(out))
    steady = step[RATE: 3 * RATE].max()
    assert step[4 * RATE - 2400: 4 * RATE + 2400].max() < 1.5 * steady
    assert step[8 * RATE - 2400: 8 * RATE + 2400].max() < 1.5 * steady


def test_far_teleport_does_not_click(make_scene, sine, tiers):
    tiers(lambda i, c: False)
    frames = np.arange(1, 182, dtype=float)
    pos = np.where(frames[:, None] < 90, [[-30.0, 40.0, 0.0]], [[30.0, 40.0, 0.0]])
    out = render.render(make_scene([{"sample": sine}], pos[:, None, :], frame_end=180, settings=PLAIN)).audio
    step = np.abs(np.diff(out, axis=0)).max(axis=1)
    jump = int(round((89 / 30 + 50 / C) * RATE))
    assert step[jump - 2400: jump + 2400].max() < 1.05 * step[RATE: 2 * RATE].max()


def test_lod_render_is_deterministic_and_stems_sum(make_scene, noise, sine):
    sources = [{"sample": noise, "group": "a", "gain_db": -6.0 * k} for k in range(4)] + [{"sample": sine, "group": "b"}]
    pos = [[10.0 * (k + 1), 20.0, 0.0] for k in range(5)]
    scene = make_scene(sources, pos, frame_end=240, settings={**PLAIN, "detail_voices": 1})
    one = render.render(scene, workers=1, stems=True)
    many = render.render(scene, workers=4, stems=True)
    assert one.lod["far_sources"] == 3 and one.lod["near_voices_max"] <= 2
    assert np.array_equal(one.audio, many.audio)
    total = sum(one.stems.values())
    assert np.abs(total - one.audio).max() < 1e-5


def test_tier_switches_keep_the_level_with_the_hybrid_panner(make_scene, noise, tiers):
    tiers(lambda i, c: c == 1)
    settings = {"cull_db": None, "air_absorption": 0.0}
    scene = make_scene([{"sample": noise, "pitch": 0.9}], [[10.0, 10.0, 0.0]], frame_end=359, settings=settings)
    out = render.render(scene).audio.sum(axis=1)
    level = [rms_db(out[a - 2400:a + 2400]) for a in (RATE * 2, RATE * 4, RATE * 6, RATE * 8, RATE * 10)]
    assert max(level) - min(level) < 1.5
