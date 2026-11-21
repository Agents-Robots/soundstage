"""End to end with Blender: build the flyby example, scan, bake, render, preview (marker ``blender``)."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from soundstage.cli import main

from conftest import RATE, onset, rms_db

REPO = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.blender


@pytest.fixture(scope="module")
def flyby(tmp_path_factory):
    out = tmp_path_factory.mktemp("flyby")
    subprocess.run([sys.executable, str(REPO / "tools" / "make_test_samples.py")], check=True, capture_output=True)
    subprocess.run(["blender", "-b", "--factory-startup", "--python-exit-code", "1",
                    "--python", str(REPO / "examples" / "flyby.py"), "--", "--save", str(out / "flyby.blend")],
                   check=True, capture_output=True)
    return out


def test_scan_finds_the_moving_ship(flyby):
    assert main(["scan", str(flyby / "flyby.blend"), "--out", str(flyby / "scan.json")]) == 0
    scan = json.loads((flyby / "scan.json").read_text())
    ship = next(m for m in scan["moving"] if m["name"] == "Ship")
    assert ship["max_speed_m_s"] == pytest.approx(30, rel=0.05)
    assert 115 <= ship["closest_frame"] <= 125
    assert scan["tagged"] == []  # tags come from the script at bake time, not from the file


def test_scan_and_bake_from_an_installed_package_use_blenders_numpy(flyby, tmp_path):
    """#49: installed with pip, the package sits in site-packages beside the venv's numpy, which
    Blender's Python cannot load; a stand-in numpy that fails on import plays that part."""
    site = tmp_path / "site-packages"
    shutil.copytree(REPO / "soundstage", site / "soundstage", ignore=shutil.ignore_patterns("__pycache__"))
    (site / "numpy").mkdir()
    (site / "numpy" / "__init__.py").write_text("raise ImportError('the venv numpy')\n")
    run = ["--run", str(REPO / "examples" / "flyby_sounds.py")]
    for script, args in (("scan.py", ["--out", str(tmp_path / "scan.json")]),
                         ("bake.py", ["--out", str(tmp_path / "bake"), "--substeps", "1", *run])):
        r = subprocess.run(["blender", "-b", str(flyby / "flyby.blend"), "--factory-startup", "-y", "--python-exit-code",
                            "1", "--python", str(site / "soundstage" / "blender" / script), "--", *args],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout[-3000:]
    assert (tmp_path / "bake" / "scene.npz").exists()


def test_bake_and_render(flyby):
    bake_dir = flyby / "bake"
    assert main(["bake", str(flyby / "flyby.blend"), "--run", str(REPO / "examples" / "flyby_sounds.py"),
                 "--out", str(bake_dir)]) == 0
    manifest = json.loads((bake_dir / "scene.json").read_text())
    assert {s["id"] for s in manifest["sources"]} == {"Ambience:0", "Beacon:0", "Crate:0", "Ship:0", "Ship:1"}

    assert main(["render", str(bake_dir / "scene.json"), "-o", str(flyby / "mix.wav"), "--report"]) == 0
    audio, rate = sf.read(flyby / "mix.wav")
    assert rate == RATE and len(audio) == 240 * 1600
    report = json.loads((flyby / "mix.report.json").read_text())
    assert all(s["audible_frames"] > 0 for s in report["sources"])

    assert main(["render", str(bake_dir / "scene.json"), "-o", str(flyby / "crate.wav"), "--solo", "Crate:*"]) == 0
    crate, _ = sf.read(flyby / "crate.wav")
    arrays = np.load(bake_dir / "scene.npz")
    k = int(np.argmin(np.abs(arrays["frames"] - 180)))
    track = next(s["track"] for s in manifest["sources"] if s["id"] == "Crate:0")
    distance = np.linalg.norm(arrays["src_pos"][k, track] - arrays["listener_matrix"][k, :3, 3])
    expected = 179 * 1600 + distance / 343.0 * RATE  # impact at frame 180, heard after its travel time
    assert abs(onset(crate, threshold=0.01 * np.abs(crate).max()) - expected) <= 20
    assert rms_db(crate[:, 1]) > rms_db(crate[:, 0])  # crate is right of the camera
    assert arrays["src_fwd"].shape == arrays["src_pos"].shape
    assert np.allclose(np.linalg.norm(arrays["src_fwd"], axis=2), 1.0, atol=1e-5)

    assert main(["render", str(bake_dir / "scene.json"), "-o", str(flyby / "ship.wav"), "--solo", "Ship:0"]) == 0
    ship, _ = sf.read(flyby / "ship.wav")
    first, last = ship[:RATE], ship[-RATE:]
    assert rms_db(first[:, 0]) > rms_db(first[:, 1]) + 10  # starts on the left
    assert rms_db(last[:, 1]) > rms_db(last[:, 0]) + 10  # ends on the right
    middle = ship[3 * RATE: 5 * RATE]
    assert rms_db(middle) > rms_db(first) + 6  # louder when close
    assert np.isfinite(ship).all()


def test_tags_survive_save_and_reload(flyby, tmp_path):
    script = tmp_path / "check.py"
    script.write_text(f"""
import sys, runpy, bpy
sys.path.insert(0, {str(REPO)!r})
runpy.run_path({str(REPO / "examples" / "flyby_sounds.py")!r})
path = {str(tmp_path / "tagged.blend")!r}
bpy.ops.wm.save_as_mainfile(filepath=path)
bpy.ops.wm.open_mainfile(filepath=path)
from soundstage.blender import tag
entries = tag.get_sounds(bpy.data.objects["Beacon"])
assert entries[0]["frame"] == [float(f) for f in range(1, 241, 30)], entries
assert tag.get_scene_settings()["samples_root"].endswith("samples/")
print("TAGS_OK")
""")
    proc = subprocess.run(["blender", "-b", str(flyby / "flyby.blend"), "--factory-startup", "--python-exit-code", "1",
                           "--python", str(script)], capture_output=True, text=True)
    assert "TAGS_OK" in proc.stdout, proc.stdout[-2000:] + proc.stderr[-2000:]


FRAMES_SCRIPT = """
import bpy, sys
s = bpy.context.scene
s.render.engine = "CYCLES"
s.cycles.samples = 1
s.cycles.use_denoising = False
s.render.resolution_x, s.render.resolution_y, s.render.resolution_percentage = 64, 36, 100
s.render.image_settings.file_format = "PNG"
s.render.filepath = sys.argv[sys.argv.index("--") + 1]
bpy.ops.render.render(animation=True)
"""


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not on PATH")
def test_preview_of_rendered_frames(flyby, tmp_path):
    script = tmp_path / "frames.py"
    script.write_text(FRAMES_SCRIPT)
    subprocess.run(["blender", "-b", str(flyby / "flyby.blend"), "--factory-startup", "--python-exit-code", "1",
                    "--python", str(script), "--", str(tmp_path / "frames" / "")], check=True, capture_output=True)
    bake_dir = tmp_path / "bake"
    assert main(["bake", str(flyby / "flyby.blend"), "--run", str(REPO / "examples" / "flyby_sounds.py"),
                 "--out", str(bake_dir), "--substeps", "1", "--pad", "0"]) == 0
    mix = tmp_path / "crate.wav"
    assert main(["render", str(bake_dir / "scene.json"), "-o", str(mix), "--solo", "Crate:*", "--report"]) == 0
    assert main(["preview", str(mix), "--frames", str(tmp_path / "frames"), "--width", "0"]) == 0
    mp4 = tmp_path / "crate_preview.mp4"
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-count_packets", "-show_entries", "stream=codec_type,nb_read_packets,r_frame_rate",
         "-of", "json", str(mp4)], capture_output=True, text=True, check=True).stdout)["streams"]
    video = next(s for s in probe if s["codec_type"] == "video")
    assert int(video["nb_read_packets"]) == 240 and video["r_frame_rate"] == "30/1"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), "-f", "f32le", "-ac", "2", "-ar", str(RATE), "-"],
                         capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)
    loud = np.nonzero(np.abs(audio).max(axis=1) > 0.1 * np.abs(audio).max())[0]
    mixed, _ = sf.read(mix)
    in_mix = np.nonzero(np.abs(mixed).max(axis=1) > 0.1 * np.abs(mixed).max())[0][0]
    assert abs(loud[0] - in_mix) <= 48  # the MP4 keeps the WAV's timing to within 1 ms


def test_bake_and_scan_a_named_scene(flyby, tmp_path):
    build = tmp_path / "second.py"
    build.write_text(f"""
import bpy
s = bpy.data.scenes.new("Second")
s.frame_start, s.frame_end = 10, 40
cam = bpy.data.objects.new("Cam2", bpy.data.cameras.new("Cam2"))
src = bpy.data.objects.new("Horn", None)
for o in (cam, src):
    s.collection.objects.link(o)
s.camera = cam
src.location = (3, 0, 0)
bpy.ops.wm.save_as_mainfile(filepath={str(tmp_path / "two.blend")!r})
""")
    subprocess.run(["blender", "-b", str(flyby / "flyby.blend"), "--factory-startup", "--python-exit-code", "1",
                    "--python", str(build)], check=True, capture_output=True)
    tags = tmp_path / "tags.py"
    tags.write_text(f"""
import sys, bpy
sys.path.insert(0, {str(REPO)!r})
from soundstage.blender import tag
tag.add_sound(bpy.context.scene.objects["Horn"], {str(REPO / "samples" / "beep.wav")!r}, mode="once", frame=20)
""")
    assert main(["bake", str(tmp_path / "two.blend"), "--scene", "Second", "--run", str(tags),
                 "--out", str(tmp_path / "bake")]) == 0
    manifest = json.loads((tmp_path / "bake" / "scene.json").read_text())
    assert manifest["scene"] == "Second"
    assert (manifest["time"]["frame_start"], manifest["time"]["frame_end"]) == (10, 40)
    assert manifest["listener"]["objects"] == ["Cam2"]
    assert [s["id"] for s in manifest["sources"]] == ["Horn:0"]
    assert main(["scan", str(tmp_path / "two.blend"), "--scene", "Second", "--out", str(tmp_path / "scan.json")]) == 0
    assert json.loads((tmp_path / "scan.json").read_text())["cameras"][0]["name"] == "Cam2"
    assert main(["bake", str(tmp_path / "two.blend"), "--scene", "Nope", "--out", str(tmp_path / "x")]) == 1


def test_blender_speaker_baseline(flyby, tmp_path):
    tags = tmp_path / "crate.py"
    tags.write_text(f"""
import sys, bpy
sys.path.insert(0, {str(REPO)!r})
from soundstage.blender import tag
tag.set_scene_settings(samples_root={str(REPO / "samples")!r} + "/")
tag.add_sound(bpy.data.objects["Crate"], "click.wav", mode="once", frame=180, ref_distance=5)
""")
    out = tmp_path / "baseline.wav"
    subprocess.run(["blender", "-b", str(flyby / "flyby.blend"), "--factory-startup", "-y", "--python-exit-code", "1",
                    "--python", str(REPO / "tools" / "blender_mixdown.py"), "--", "--run", str(tags), "--out", str(out)],
                   check=True, capture_output=True)
    audio, rate = sf.read(out)
    assert rate == RATE and len(audio) == 240 * 1600
    assert onset(audio, threshold=0.1 * np.abs(audio).max()) == 179 * 1600  # same frame as soundstage
    assert np.abs(audio[:, 1]).max() > np.abs(audio[:, 0]).max()  # crate on the right


def test_bake_records_marker_camera_switches_and_warns_about_padding(flyby, tmp_path):
    build = tmp_path / "switch.py"
    build.write_text(f"""
import bpy
s = bpy.context.scene
cam2 = bpy.data.objects.new("Camera2", bpy.data.cameras.new("Camera2"))
s.collection.objects.link(cam2)
cam2.location = (0, -50, 1.7)
cam2.rotation_euler = (1.5708, 0, 0)
m1 = s.timeline_markers.new("A", frame=1)
m1.camera = s.objects["Camera"]
m2 = s.timeline_markers.new("B", frame=100)
m2.camera = cam2
bpy.ops.wm.save_as_mainfile(filepath={str(tmp_path / "switch.blend")!r})
""")
    subprocess.run(["blender", "-b", str(flyby / "flyby.blend"), "--factory-startup", "--python-exit-code", "1",
                    "--python", str(build)], check=True, capture_output=True)
    out = tmp_path / "bake"
    assert main(["bake", str(tmp_path / "switch.blend"), "--run", str(REPO / "examples" / "flyby_sounds.py"),
                 "--out", str(out), "--pad", "0", "--substeps", "1"]) == 0
    manifest = json.loads((out / "scene.json").read_text())
    arrays = np.load(out / "scene.npz")
    assert manifest["listener"]["objects"] == ["Camera", "Camera2"]
    assert list(arrays["cuts"]) == [100.0]
    assert any(w.startswith("padding 0.00 s") for w in manifest["warnings"])
    assert main(["render", str(out / "scene.json"), "-o", str(tmp_path / "mix.wav")]) == 0


def test_padding_warning_counts_only_sound_emitted_before_the_first_frame(flyby, tmp_path):
    """#44: a source on a second set, 2000 m from the first shot's camera, that starts with its own
    shot needs no padding. A source playing from before the first frame does: heard by the second
    camera (1657 m away) at frame 50, its sound left it 1657 / 343 - 49 / 30 = 3.20 s before frame 1."""
    build = tmp_path / "sets.py"
    build.write_text(f"""
import sys
sys.path.insert(0, {str(REPO)!r})
import bpy
from soundstage.blender import tag
bpy.ops.wm.read_factory_settings(use_empty=True)
s = bpy.context.scene
s.frame_start, s.frame_end = 1, 100
s.render.fps = 30
def obj(name, data, location):
    o = bpy.data.objects.new(name, data)
    s.collection.objects.link(o)
    o.location = location
    return o
cam_a = obj("CamA", bpy.data.cameras.new("CamA"), (0, 0, 1.6))
cam_b = obj("CamB", bpy.data.cameras.new("CamB"), (2000, 0, 1.6))
for frame, cam in ((1, cam_a), (50, cam_b)):
    s.timeline_markers.new(cam.name, frame=frame).camera = cam
tag.add_sound(obj("Far", None, (2000, 10, 1.6)), {str(REPO / "samples" / "engine_hum.wav")!r}, frame=50,
              id="far")
tag.add_sound(obj("Near", None, (343, 0, 1.6)), {str(REPO / "samples" / "engine_hum.wav")!r}, id="near")
bpy.ops.wm.save_as_mainfile(filepath={str(tmp_path / "sets.blend")!r})
""")
    subprocess.run(["blender", "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(build)],
                   check=True, capture_output=True)
    out = tmp_path / "bake"
    assert main(["bake", str(tmp_path / "sets.blend"), "--out", str(out), "--pad", "0.5", "--substeps", "1"]) == 0
    warnings = [w for w in json.loads((out / "scene.json").read_text())["warnings"] if w.startswith("padding")]
    assert len(warnings) == 1
    assert "1 source(s)" in warnings[0] and "up to 3.20 s, near" in warnings[0] and "--pad 3.2 " in warnings[0]
