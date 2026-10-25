"""Render and output with synthetic scenes (no Blender)."""

import numpy as np
import pytest
import soundfile as sf

from soundstage.engine import mix, render
from soundstage.engine.report import metrics

from conftest import RATE, onset, peak_index, rms_db


PLAIN = {"panner": "amplitude", "air_absorption": 0.0}  # distance gain and pan only


def test_level_drops_6db_at_twice_the_reference_distance(make_scene, sine):
    near = make_scene([{"sample": sine, "ref_distance": 5}], [[0, 5, 0]], settings=PLAIN)
    far = make_scene([{"sample": sine, "ref_distance": 5}], [[0, 10, 0]], settings=PLAIN)
    a, b = render.render(near).audio, render.render(far).audio
    assert rms_db(b) - rms_db(a) == pytest.approx(-6.02, abs=0.1)


def test_source_in_front_is_centred_at_minus_3db(make_scene, sine):
    out = render.render(make_scene([{"sample": sine, "loop_phase": 0.0}], [[0, 1, 0]], settings=PLAIN)).audio
    assert np.allclose(out[:, 0], out[:, 1])
    assert rms_db(out[:, 0]) == pytest.approx(rms_db(0.5 * np.sin(np.linspace(0, 2000 * np.pi, 96000))) - 3.01, abs=0.05)


def test_source_on_the_right_is_louder_right(make_scene, sine):
    out = render.render(make_scene([{"sample": sine}], [[10, 1, 0]])).audio
    assert rms_db(out[:, 1]) - rms_db(out[:, 0]) > 20


def test_one_shot_onset_and_output_length(make_scene, click):
    scene = make_scene([{"sample": click, "mode": "once", "frame": 120, "sync_to_picture": True}], [[0, 1, 0]],
                       frame_end=240, settings=PLAIN)
    result = render.render(scene)
    assert len(result.audio) == 240 * 1600
    assert peak_index(result.audio) == 190400  # band-limited reads ring symmetrically around the click


def test_moving_source_pans_left_to_right(make_scene, sine):
    n = 61  # baked frames 1..61
    x = np.linspace(-50, 50, n)
    pos = np.stack([x, np.full(n, 10.0), np.zeros(n)], axis=1)[:, None, :]
    out = render.render(make_scene([{"sample": sine}], pos)).audio
    first, last = out[: RATE // 4], out[-RATE // 4:]
    assert rms_db(first[:, 0]) > rms_db(first[:, 1]) + 10
    assert rms_db(last[:, 1]) > rms_db(last[:, 0]) + 10


def test_bed_ignores_position_and_keeps_stereo(make_scene, wav):
    path = wav("bed.wav", np.stack([np.full(RATE, 0.5), np.zeros(RATE)], axis=1))
    out = render.render(make_scene([{"sample": path, "spatial": False}])).audio
    assert np.allclose(out[:, 0], 0.5, atol=1e-3) and np.allclose(out[:, 1], 0.0)


def test_frame_subrange_starts_at_its_first_frame(make_scene, click):
    scene = make_scene([{"sample": click, "mode": "once", "frame": 50, "sync_to_picture": True}], [[0, 1, 0]],
                       settings=PLAIN)
    result = render.render(scene, frames=(41, 60))
    assert len(result.audio) == 20 * 1600
    assert peak_index(result.audio) == 9 * 1600


def test_solo_and_mute(make_scene, sine, click):
    scene = make_scene([{"sample": sine, "group": "engines"}, {"sample": click, "mode": "once", "frame": 1}],
                       [[[0, 1, 0], [0, 1, 0]]])
    assert [s["id"] for s in render.render(scene, solo=["group:engines"]).sources] == ["source:0"]
    assert [s["id"] for s in render.render(scene, mute=["source:0"]).sources] == ["source:1"]


def test_render_is_deterministic(make_scene, sine, tmp_path):
    scene = make_scene([{"sample": sine}], [[3, 4, 0]])
    a = mix.write_wav(tmp_path / "a.wav", render.render(scene).audio, RATE)
    b = mix.write_wav(tmp_path / "b.wav", render.render(scene).audio, RATE)
    assert a.read_bytes() == b.read_bytes()


def test_pcm24_output(make_scene, sine, tmp_path):
    path = mix.write_wav(tmp_path / "p.wav", render.render(make_scene([{"sample": sine}], [[0, 1, 0]])).audio,
                         RATE, pcm24=True)
    assert sf.info(path).subtype == "PCM_24"


def test_unimplemented_parameters_are_warned(make_scene, sine):
    result = render.render(make_scene([{"sample": sine, "gain_jitter_db": 2.0}], [[0, 1, 0]]))
    assert any("'gain_jitter_db' is not implemented" in w for w in result.warnings)


def test_metrics_of_a_full_scale_sine():
    t = np.arange(RATE * 2) / RATE
    x = np.sin(2 * np.pi * 997 * t)
    m = metrics(np.stack([x, x], axis=1), RATE)
    assert m["peak_dbfs"] == pytest.approx(0.0, abs=0.01)
    assert m["lufs_integrated"] == pytest.approx(0.0, abs=0.5)  # BS.1770: stereo 0 dBFS sine ~ 0 LUFS
