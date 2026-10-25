"""End to end with Blender: build the flyby example, scan, bake, render (marker ``blender``)."""

import json
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
