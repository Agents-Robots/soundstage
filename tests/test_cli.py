"""Command-line checks: argument validation, file names, warnings and summaries (no Blender)."""

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from soundstage.cli import blender_path, main

from conftest import static_listener


@pytest.mark.parametrize("frames", ["abc", "40-20", "0-10", "50-90"])
def test_render_rejects_frames_outside_the_scene(make_scene, sine, tmp_path, capsys, frames):
    scene = make_scene([{"sample": sine}], [[0, 10, 0]])  # frames 1-60
    assert main(["render", str(scene.path), "-o", str(tmp_path / "m.wav"), "--frames", frames]) == 1
    assert "--frames" in capsys.readouterr().err
    assert not (tmp_path / "m.wav").exists()


def test_plot_without_spatial_sources_is_skipped(make_scene, wav, tmp_path, capsys):
    bed = wav("bed.wav", np.full((48000, 2), 0.1))
    scene = make_scene([{"sample": bed, "spatial": False}])
    assert main(["render", str(scene.path), "-o", str(tmp_path / "m.wav"), "--plot"]) == 0
    assert "nothing to plot" in capsys.readouterr().out
    assert not (tmp_path / "m.plot.png").exists()


def test_stem_names_are_safe_file_names(make_scene, sine, tmp_path):
    scene = make_scene([{"sample": sine, "group": "engines/left side"}], [[0, 10, 0]])
    assert main(["render", str(scene.path), "-o", str(tmp_path / "m.wav"), "--stems"]) == 0
    assert (tmp_path / "m_stem_engines_left_side.wav").exists()


def test_bake_settings_overridden_at_render_time_are_warned(make_scene, sine, tmp_path):
    scene = make_scene([{"sample": sine}], [[0, 10, 0]])
    out = tmp_path / "m.wav"
    assert main(["render", str(scene.path), "-o", str(out), "--set", "occlusion_rate=5", "--report"]) == 0
    warnings = json.loads(out.with_suffix(".report.json").read_text())["warnings"]
    assert any("occlusion_rate" in w and "bake" in w for w in warnings)


def test_empty_selection_is_warned(make_scene, sine, tmp_path):
    scene = make_scene([{"sample": sine}], [[0, 10, 0]])
    assert main(["render", str(scene.path), "-o", str(tmp_path / "m.wav"), "--solo", "nothing", "--strict"]) == 1


def test_source_peaks_include_the_master_gain(make_scene, sine, tmp_path):
    scene = make_scene([{"sample": sine}], [[0, 10, 0]])
    peaks = []
    for gain in (0, -6):
        out = tmp_path / f"m{gain}.wav"
        assert main(["render", str(scene.path), "-o", str(out), "--set", f"master_gain_db={gain}", "--report"]) == 0
        peaks.append(json.loads(out.with_suffix(".report.json").read_text())["sources"][0]["peak_dbfs"])
    assert peaks[1] - peaks[0] == pytest.approx(-6.0, abs=0.01)


def test_inspect_ignores_the_jump_at_a_camera_cut(make_scene, sine, capsys):
    listener = static_listener(61)
    listener[30:, :3, 3] = [0, -200, 0]  # the second camera is 200 m further back
    scene = make_scene([{"sample": sine}], [[0, 10, 0]], listener=listener, cuts=[31])
    assert main(["inspect", str(scene.path), "--json"]) == 0
    row = json.loads(capsys.readouterr().out)["sources"][0]
    assert row["distance_m"] == [10.0, 210.0]
    assert row["max_radial_speed_m_s"] == 0.0 and row["rate"] == [1.0, 1.0]


def test_blender_path_is_the_checkout_or_a_folder_with_only_the_package(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    assert blender_path(repo / "soundstage") == repo
    site = tmp_path / "site-packages"
    shutil.copytree(repo / "soundstage", site / "soundstage", ignore=shutil.ignore_patterns("__pycache__"))
    (site / "numpy").mkdir()
    folder = blender_path(site / "soundstage", cache=tmp_path / "cache")
    assert [p.name for p in folder.iterdir()] == ["soundstage"]
    assert (folder / "soundstage").resolve() == (site / "soundstage").resolve()
    assert blender_path(site / "soundstage", cache=tmp_path / "cache") == folder
    shutil.copytree(site, tmp_path / "other")
    assert blender_path(tmp_path / "other" / "soundstage", cache=tmp_path / "cache") != folder
