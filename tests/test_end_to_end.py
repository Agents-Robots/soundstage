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
    assert abs(onset(crate) - 179 * 1600) <= 2  # impact at frame 180
    assert rms_db(crate[:, 1]) > rms_db(crate[:, 0])  # crate is right of the camera

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
    assert abs(loud[0] - 179 * 1600) <= 48  # the impact at frame 180, within 1 ms


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
