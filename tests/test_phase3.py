"""Occlusion, reverb, stems, loudness, limiter, plot (Phase 3), on synthetic scenes (no Blender)."""

import json

import numpy as np
import pytest
import soundfile as sf
from scipy.signal import csd, welch

from soundstage.cli import main
from soundstage.engine import filters, mix, render, report, reverb

from conftest import RATE, rms_db

PLAIN = {"panner": "amplitude", "air_absorption": 0.0, "doppler_factor": 0.0}


def _band_db(x, y, f):
    fr, pxy = csd(x, y, fs=RATE, nperseg=4096)
    _, pxx = welch(x, fs=RATE, nperseg=4096)
    return np.interp(f, fr, 20 * np.log10(np.abs(pxy / pxx)))


def _occlusion_scene(make_scene, sample, vis_value, settings=None, **source):
    frames = np.array([1.0, 30.0, 31.0, 90.0])
    v = np.ones((4, 1, 3))
    v[2:] = vis_value
    return make_scene([{"sample": sample, **source}], [[0, 10, 0]], frame_end=90,
                      settings={**PLAIN, **(settings or {})}, visibility=(frames, v))


def test_fully_occluded_source_drops_by_the_transmission_and_is_low_passed(make_scene, wav):
    noise = wav("noise.wav", np.random.default_rng(4).standard_normal(RATE * 2) * 0.1)
    out = render.render(_occlusion_scene(make_scene, noise, 0.0, loop_phase=0.0)).audio[:, 0]
    ref = render.render(_occlusion_scene(make_scene, noise, 1.0, loop_phase=0.0)).audio[:, 0]
    late = slice(int(2.0 * RATE), int(3.0 * RATE))
    h = _band_db(ref[late], out[late], np.array([200.0, 1500.0, 6000.0]))
    assert h[0] == pytest.approx(-12.0, abs=0.3)  # occlusion_gain_db
    assert h[1] == pytest.approx(-12.0 - 3.0, abs=0.6)  # transmission low-pass at occlusion_cutoff_hz
    assert h[2] < h[1] - 6


def test_occlusion_cutoff_is_the_least_squares_fit_in_db():
    f = np.array([1000.0, 4000.0])
    assert filters.fit_onepole_cutoff((1 / np.sqrt(1 + (f / 1524.0) ** 2))[None], f)[0] == pytest.approx(1524.0)
    ratios = np.sort(np.random.default_rng(0).uniform(0.02, 1.0, (100, 2)), axis=1)[:, ::-1]
    grid = np.geomspace(20, 1e6, 100000)  # reference: brute force over cutoffs
    err = ((10 * np.log10(1 + (f / grid[:, None]) ** 2)[None] + 20 * np.log10(ratios)[:, None, :]) ** 2).sum(axis=2)
    assert filters.fit_onepole_cutoff(ratios, f) == pytest.approx(grid[np.argmin(err, axis=1)], rel=2e-4)


def test_report_has_the_visibility_range(make_scene, sine):
    res = render.render(_occlusion_scene(make_scene, sine, 0.0))
    st = res.sources[0]
    assert st["visibility"] == [0.0, 1.0] and 55 <= st["occluded_frames"] <= 61


def test_occlusion_transition_is_smooth(make_scene, sine):
    out = render.render(_occlusion_scene(make_scene, sine, 0.0)).audio[:, 0]
    seg = out[int(0.9 * RATE): int(1.5 * RATE)]
    env = np.sqrt((seg[: len(seg) // 48 * 48].reshape(-1, 48) ** 2).mean(axis=1))
    assert np.abs(np.diff(20 * np.log10(env + 1e-9))).max() < 0.5  # dB per ms
    assert np.abs(np.diff(seg)).max() <= 2 * np.pi * 1000 / RATE * np.abs(seg).max() * 1.5


def test_partial_visibility_lowpasses_more_where_bands_are_blocked(make_scene, wav):
    noise = wav("noise.wav", np.random.default_rng(5).standard_normal(RATE * 2) * 0.1)
    frames = np.array([1.0, 90.0])
    v = np.array([[[1.0, 0.6, 0.2]], [[1.0, 0.6, 0.2]]])  # low band open, high band mostly blocked
    occ = render.render(make_scene([{"sample": noise, "loop_phase": 0.0}], [[0, 10, 0]], frame_end=90, settings=PLAIN,
                                   visibility=(frames, v))).audio[:, 0]
    ref = render.render(make_scene([{"sample": noise, "loop_phase": 0.0}], [[0, 10, 0]], frame_end=90,
                                   settings=PLAIN)).audio[:, 0]
    h = _band_db(ref[RATE:], occ[RATE:], np.array([250.0, 1000.0, 4000.0]))
    assert abs(h[0]) < 0.5 and h[2] < h[1] < h[0]


def test_obstruction_keeps_the_reverb_send_and_occlusion_reduces_it(make_scene, sine):
    wet = {}
    for mode in ("obstruction", "occlusion"):
        res = render.render(_occlusion_scene(make_scene, sine, 0.0, settings={"reverb": "room"}, occlusion_mode=mode),
                            stems=True)
        wet[mode] = rms_db(res.stems["reverb"][int(2 * RATE):])
    assert wet["occlusion"] < wet["obstruction"] - 10


def test_decay_curve_has_the_preset_decay_times_away_from_the_references():
    for name in ("concerthall", "hangar", "castle_cupboard", "icepalace_hall"):
        p = reverb.preset(name)
        f = np.array([p["lf_reference"] / 4, np.sqrt(p["lf_reference"] * p["hf_reference"]), p["hf_reference"] * 4])
        assert reverb.decay_curve(f, p) == pytest.approx(reverb.decay_times(p), rel=0.02), name


def test_impulse_response_decays_as_the_curve_in_every_octave_band():
    # measured T30 per octave band against the T30 the curve predicts for that band filter; single
    # noise realizations scatter by about 13 % for short decays in narrow bands (ISO 3382 B*T)
    for name in ("generic", "concerthall", "hangar", "city", "forest", "spacestation_hall", "sewerpipe", "underwater",
                 "icepalace_mediumroom", "castle_cupboard"):
        p = reverb.preset(name)
        ir = reverb.synthesize(p, RATE, reverb.seed_for(name))
        errors = []
        for c in 1000 * 2.0 ** np.arange(-4, 5):
            band = (c / np.sqrt(2), min(c * np.sqrt(2), 0.45 * RATE))
            expected = reverb.expected_rt60(p, RATE, band)
            if expected >= 12 / c:  # longer than the band filter's own ringing
                errors.append(abs(reverb.rt60(ir, RATE, band) / expected - 1))
        assert np.median(errors) < 0.04 and max(errors) < 0.15, name


def test_reverb_is_decorrelated_and_deterministic():
    a = reverb.synthesize(reverb.preset("concerthall"), RATE, reverb.seed_for("concerthall"))
    b = reverb.synthesize(reverb.preset("concerthall"), RATE, reverb.seed_for("concerthall"))
    assert np.array_equal(a, b) and abs(np.corrcoef(a.T)[0, 1]) < 0.05
    with pytest.raises(ValueError, match="did you mean"):
        reverb.preset("hangr")


def test_direct_to_reverberant_ratio_falls_6db_per_doubling(make_scene, sine):
    drr = []
    for d in (5.0, 10.0, 20.0):
        res = render.render(make_scene([{"sample": sine, "ref_distance": 5.0}], [[0, d, 0]], frame_end=90,
                                       settings={**PLAIN, "reverb": "concerthall", "reverb_send_law": "efx"}),
                            stems=True)
        drr.append(rms_db(res.stems["sfx"][2 * RATE:]) - rms_db(res.stems["reverb"][2 * RATE:]))
    assert np.diff(drr) == pytest.approx([-6.02, -6.02], abs=0.3)  # room rolloff 0: reverb level stays


def test_reverb_send_follows_the_revised_theory_then_spreading(make_scene, sine):
    # living room, T60 0.5 s: within c T / ln(1000) = 24.8 m the reverberation falls 60 dB per c T
    # (Barron and Lee), beyond it 6 dB per doubling; both meet with the same slope
    law = reverb.SendLaw(0.0, reverb.decay_times(reverb.preset("livingroom"))[1], None, 343.0)
    assert law.radius == pytest.approx(343.0 * 0.5 / np.log(1000.0))
    r = law.radius
    slope = np.diff(np.log(law.factor(np.array([r * 0.999, r, r * 1.001])))) / np.log(1.001)
    assert slope == pytest.approx([-1.0, -1.0], abs=0.002)
    level = {}
    for d in (10.0, 20.0, 50.0, 100.0):
        res = render.render(make_scene([{"sample": sine}], [[0, d, 0]], frame_end=90,
                                       settings={**PLAIN, "reverb": "livingroom"}), stems=True)
        level[d] = rms_db(res.stems["reverb"][2 * RATE:])
    for d1, d2 in ((10.0, 20.0), (20.0, 50.0), (50.0, 100.0)):
        want = 20 * np.log10(law.factor(np.array([d2]))[0] / law.factor(np.array([d1]))[0])
        assert level[d2] - level[d1] == pytest.approx(want, abs=0.3)


def test_reverb_bus_chunks_equal_one_convolution():
    env = reverb.environment("room", RATE)
    x = np.random.default_rng(3).standard_normal(RATE)
    whole = reverb.ReverbBus(env).process(x)
    bus = reverb.ReverbBus(env)
    parts = np.concatenate([bus.process(x[:12345]), bus.process(x[12345:])])
    assert np.allclose(parts, whole, atol=1e-12)


def test_stems_sum_to_the_master(make_scene, sine, click):
    scene = make_scene([{"sample": sine, "group": "engines"}, {"sample": click, "mode": "once", "frame": 20},
                        {"sample": sine, "spatial": False, "group": "ambience", "gain_db": -12}],
                       [[[3, 10, 0], [-2, 5, 0]]], settings={"reverb": "city"})
    res = render.render(scene, stems=True)
    assert set(res.stems) == {"engines", "sfx", "ambience", "reverb"}
    assert np.abs(sum(res.stems.values()) - res.audio).max() < 1e-6  # float32 stems


def test_normalize_and_limit(make_scene, wav, tmp_path):
    loud = wav("loud.wav", np.random.default_rng(6).standard_normal(RATE * 4) * 0.5)
    scene = make_scene([{"sample": loud, "spatial": False}], frame_end=150)
    out = tmp_path / "mix.wav"
    assert main(["render", str(scene.path), "-o", str(out), "--normalize", "-8", "--limit", "-1", "--stems",
                 "--report"]) == 0
    audio, _ = sf.read(out)
    m = report.metrics(audio, RATE)
    assert m["lufs_integrated"] == pytest.approx(-8, abs=0.5) and m["true_peak_dbtp"] <= -1.0 + 0.05
    stem, _ = sf.read(mix.stem_path(out, "sfx"))
    assert np.abs(stem - audio).max() < 1e-6  # the limiter's gain is applied to the stems too
    rep = json.loads(out.with_suffix(".report.json").read_text())
    assert rep["processing"]["limiter_max_reduction_db"] > 0 and "loudness_range_lu" in rep["master"]


def test_report_lufs_and_true_peak_match_references(make_scene, sine, tmp_path):
    out = tmp_path / "mix.wav"
    assert main(["render", str(make_scene([{"sample": sine}], [[2, 5, 0]], frame_end=150).path), "-o", str(out),
                 "--report"]) == 0
    audio, _ = sf.read(out)
    import pyloudnorm
    rep = json.loads(out.with_suffix(".report.json").read_text())["master"]
    assert rep["lufs_integrated"] == pytest.approx(pyloudnorm.Meter(RATE).integrated_loudness(audio), abs=0.01)
    # true peak between samples: a sine at fs/4 with 45 degrees phase has its sample peaks 3.01 dB
    # below the true peak (EBU Tech 3341 true-peak case); faded in and out, since a hard start rings
    t = np.arange(2 * RATE) / RATE
    fade = np.clip(np.minimum(t, t[-1] - t) / 0.1, 0, 1)
    x = 0.5 * np.sin(2 * np.pi * RATE / 4 * t + np.pi / 4) * fade
    m = report.metrics(np.stack([x, x], axis=1), RATE)
    assert m["peak_dbfs"] == pytest.approx(-9.03, abs=0.01)
    assert m["true_peak_dbtp"] == pytest.approx(-6.02, abs=0.1)


@pytest.mark.parametrize("pair,expected", [((-20, -30), 10.0), ((-20, -15), 5.0), ((-40, -20), 20.0)])
def test_loudness_range_matches_ebu_tech_3342_cases(pair, expected):
    t = np.arange(20 * RATE) / RATE
    parts = [10 ** (db / 20) * np.sin(2 * np.pi * 1000 * t) for db in pair]
    x = np.concatenate(parts)
    assert report.loudness_range(np.stack([x, x], axis=1), RATE) == pytest.approx(expected, abs=0.1)


def test_plot_is_written(make_scene, sine, tmp_path):
    frames = np.array([1.0, 60.0])
    scene = make_scene([{"sample": sine}], [[3, 10, 0]], visibility=(frames, np.ones((2, 1, 3))))
    out = tmp_path / "mix.wav"
    assert main(["render", str(scene.path), "-o", str(out), "--plot"]) == 0
    assert out.with_suffix(".plot.png").stat().st_size > 10_000


def test_presets_command_lists_the_environments(capsys):
    assert main(["presets", "hangar"]) == 0
    out = capsys.readouterr().out
    assert "hangar" in out and "10.05" in out and "concerthall" not in out


def test_reverb_is_already_built_up_at_the_first_sample(make_scene, wav):
    noise = wav("noise.wav", np.random.default_rng(7).standard_normal(RATE * 4) * 0.1)
    scene = make_scene([{"sample": noise, "loop_phase": 0.0}], [[0, 10, 0]], frame_end=90,
                       settings={**PLAIN, "reverb": "concerthall"})
    wet = render.render(scene, frames=(61, 90), stems=True).stems["reverb"]  # 2 s of baked lead-in
    early, later = rms_db(wet[: RATE // 5]), rms_db(wet[RATE // 2: RATE])
    assert early == pytest.approx(later, abs=1.0)  # without the pre-roll the reverb rises from silence
