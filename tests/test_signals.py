"""Samples and dry timelines."""

import numpy as np

from soundstage.blender import schema
from soundstage.engine import signals

from conftest import RATE


def params(**kw):
    return schema.resolve_source({"sample": "x", **kw})


def test_resampling_keeps_duration(wav):
    path = wav("s44.wav", np.sin(np.arange(44100) / 10), rate=44100)
    assert abs(len(signals.load_sample(path, RATE)) - RATE) <= 2


def test_pitch_shortens(wav):
    path = wav("p.wav", np.sin(np.arange(RATE) / 10))
    assert abs(len(signals.load_sample(path, RATE, pitch=2.0)) - RATE // 2) <= 2


def test_downmix_and_bed_channels(wav):
    stereo = wav("st.wav", np.stack([np.full(1000, 0.4), np.full(1000, 0.2)], axis=1))
    mono = wav("mo.wav", np.full(1000, 0.5))
    assert np.allclose(signals.load_sample(stereo, RATE)[100], 0.3)
    assert signals.load_sample(stereo, RATE, stereo=True).shape == (1000, 2)
    bed = signals.load_sample(mono, RATE, stereo=True)
    assert np.allclose(bed[100], 0.5 / np.sqrt(2))


def test_one_shot_starts_at_trigger_sample():
    x = np.ones(100)
    out = signals.dry_timeline(x, params(mode="once", frame=1), RATE, 1234, None, 0, 5000, "a")
    assert out[1233] == 0 and out[1234] == 1 and out[1333] == 1 and out[1334] == 0


def test_repeated_one_shots_and_window_offset():
    x = np.ones(10)
    out = signals.dry_timeline(x, params(mode="once", frame=[1, 2]), RATE, [100, 200], None, 50, 300, "a")
    assert out.sum() == 20 and out[50] == 1 and out[150] == 1


def test_loop_seam_has_no_step():
    period = 1000
    x = np.sin(2 * np.pi * np.arange(4 * period + 37) / period)  # not a whole number of cycles
    out = signals.dry_timeline(x, params(loop_phase=0.0), RATE, None, None, 0, 20 * len(x), "a")
    max_natural = np.abs(np.diff(x)).max()
    assert np.abs(np.diff(out)).max() <= max_natural * 1.5


def test_loop_seam_keeps_level_for_correlated_and_uncorrelated_material():
    tone = np.sin(2 * np.pi * np.arange(48000) / 48)  # whole cycles: head and tail fully correlated
    noise = np.random.default_rng(2).standard_normal(48000)
    for x in (tone, noise, np.full(48000, 0.5)):
        out = signals.dry_timeline(x, params(loop_phase=0.0), RATE, None, None, 0, 3 * 48000, "a")
        seam = out[48000 - 2400 - 2000: 48000 - 2400 + 2000]  # around the first seam
        windows = seam[: len(seam) // 400 * 400].reshape(-1, 400)
        level = np.sqrt((windows ** 2).mean(axis=1))
        ref = np.sqrt((x ** 2).mean())
        assert np.all(np.abs(20 * np.log10(level / ref)) < 1.0)


def test_loop_without_crossfade_repeats_exactly():
    x = np.arange(10.0)
    out = signals.dry_timeline(x, params(loop_phase=0.0, loop_crossfade=0.0), RATE, None, None, 0, 25, "a")
    assert np.array_equal(out, np.concatenate([x, x, x[:5]]))


def test_random_phase_is_seeded_by_id():
    x = np.random.default_rng(1).standard_normal(5000)
    a = signals.dry_timeline(x, params(), RATE, None, None, 0, 100, "Ship:0")
    b = signals.dry_timeline(x, params(), RATE, None, None, 0, 100, "Ship:0")
    c = signals.dry_timeline(x, params(), RATE, None, None, 0, 100, "Ship:1")
    assert np.array_equal(a, b) and not np.array_equal(a, c)


def test_loop_start_and_end_fades():
    x = np.ones(1000)
    p = params(frame=1, end_frame=2, fade_in=0.001, fade_out=0.001, loop_crossfade=0.0)
    out = signals.dry_timeline(x, p, RATE, 1000, 2000, 0, 3000, "a")
    fade = int(0.001 * RATE)
    assert out[999] == 0 and 0 < out[1000] < 1 and out[1000 + fade] == 1
    assert out[1999] == 1 and 0 < out[2001] < 1 and out[2000 + fade] == 0
    assert np.all(np.diff(out[1000:1000 + fade + 1]) >= 0)
