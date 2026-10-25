"""Speaker objects (FR-8) and tags inside instances (FR-9), baked with Blender (marker ``blender``)."""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from soundstage.cli import main

from conftest import RATE, rms_db

REPO = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.blender

CAMERA = """
import bpy, math
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
s = bpy.context.scene
s.frame_start, s.frame_end = 1, 60
cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
s.collection.objects.link(cam)
s.camera = cam
cam.rotation_euler = (math.radians(90), 0, 0)  # looking along +Y
"""


def blender(script: str, tmp_path: Path, name: str) -> Path:
    path = tmp_path / f"{name}.py"
    path.write_text(script)
    subprocess.run(["blender", "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(path)],
                   check=True, capture_output=True)
    return tmp_path / f"{name}.blend"


def test_speaker_object_becomes_a_source(tmp_path, sine):
    blend = blender(CAMERA + f"""
s.frame_set(10)
bpy.ops.object.speaker_add(location=(0, 10, 0))
spk = bpy.context.object
spk.name = "Horn"
spk.data.sound = bpy.data.sounds.load({sine!r})
spk.data.volume = 0.5
spk.data.distance_reference = 2.0
tagged = bpy.data.objects.new("Tagged", None)
s.collection.objects.link(tagged)
tagged.location = (0, 10, 0)
bpy.ops.wm.save_as_mainfile(filepath={str(tmp_path / 'speaker.blend')!r})
""", tmp_path, "speaker")
    tags = tmp_path / "tags.py"
    tags.write_text(f"""
import sys, bpy
sys.path.insert(0, {str(REPO)!r})
from soundstage.blender import tag
tag.add_sound(bpy.data.objects["Tagged"], {sine!r}, mode="once", frame=10, gain_db=-6.0206, ref_distance=2.0)
""")
    assert main(["scan", str(blend), "--out", str(tmp_path / "scan.json")]) == 0
    scan = json.loads((tmp_path / "scan.json").read_text())
    assert scan["speakers"][0]["name"] == "Horn" and scan["speakers"][0]["strip_frames"] == [10.0]
    out = tmp_path / "bake"
    assert main(["bake", str(blend), "--run", str(tags), "--out", str(out)]) == 0
    sources = {s["id"]: s for s in json.loads((out / "scene.json").read_text())["sources"]}
    horn = sources["Horn:speaker"]
    assert horn["mode"] == "once" and horn["frame"] == [10.0] and horn["ref_distance"] == 2.0
    assert horn["gain_db"] == pytest.approx(-6.0206, abs=1e-3) and horn["forward_axis"] == "-Z"
    levels = {}
    for sid in ("Horn:speaker", "Tagged:0"):
        assert main(["render", str(out / "scene.json"), "-o", str(tmp_path / f"{sid[:4]}.wav"), "--solo", sid]) == 0
        import soundfile as sf
        audio, _ = sf.read(tmp_path / f"{sid[:4]}.wav")
        levels[sid] = rms_db(audio[RATE // 2: RATE])
    assert levels["Horn:speaker"] == pytest.approx(levels["Tagged:0"], abs=0.01)


INSTANCES = CAMERA + """
asset = bpy.data.collections.new("CarAsset")
car = bpy.data.objects.new("Car", None)
asset.objects.link(car)
car.location = (0, 0, 1)
asset.instance_offset = (0, 0, 0.5)
car["sfx"] = [{{"sample": {sine!r}, "gain_db": -3.0}}]
for i, x in enumerate((0, 10, 40)):
    e = bpy.data.objects.new(f"CarInst.{{i}}", None)
    e.instance_type = "COLLECTION"; e.instance_collection = asset
    e.location = (x, 5, 0)
    s.collection.objects.link(e)
mesh = bpy.data.meshes.new("pts"); mesh.from_pydata([(0, 20, 0), (5, 20, 0)], [], [])
gn = bpy.data.objects.new("Scatter", mesh); s.collection.objects.link(gn)
mod = gn.modifiers.new("GN", "NODES")
tree = bpy.data.node_groups.new("scatter", "GeometryNodeTree")
tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
nin = tree.nodes.new("NodeGroupInput"); nout = tree.nodes.new("NodeGroupOutput")
ci = tree.nodes.new("GeometryNodeCollectionInfo"); ci.inputs["Collection"].default_value = asset
iop = tree.nodes.new("GeometryNodeInstanceOnPoints")
tree.links.new(nin.outputs[0], iop.inputs["Points"]); tree.links.new(ci.outputs[0], iop.inputs["Instance"])
tree.links.new(iop.outputs[0], nout.inputs[0])
mod.node_group = tree
bpy.ops.mesh.primitive_cube_add(location=(0, 30, 0))  # tagged object whose geometry nodes add a curve:
sign = bpy.context.object  # the depsgraph lists it again as an instance of itself
sign.name = "Sign"
sign["sfx"] = [{{"sample": {sine!r}}}]
line = bpy.data.node_groups.new("line", "GeometryNodeTree")
line.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
line.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
lin = line.nodes.new("NodeGroupInput"); lout = line.nodes.new("NodeGroupOutput")
curve = line.nodes.new("GeometryNodeCurvePrimitiveLine"); join = line.nodes.new("GeometryNodeJoinGeometry")
line.links.new(lin.outputs[0], join.inputs[0]); line.links.new(curve.outputs[0], join.inputs[0])
line.links.new(join.outputs[0], lout.inputs[0])
sign.modifiers.new("GN", "NODES").node_group = line
{extra}
bpy.ops.wm.save_as_mainfile(filepath={path!r})
"""


def test_tags_inside_instances_become_one_source_each(tmp_path, sine):
    blend = blender(INSTANCES.format(sine=sine, extra="", path=str(tmp_path / "inst.blend")), tmp_path, "inst")
    assert main(["scan", str(blend), "--out", str(tmp_path / "scan.json")]) == 0
    assert json.loads((tmp_path / "scan.json").read_text())["instanced_tags"] == [{"object": "Car", "instances": 5}]
    out = tmp_path / "bake"
    assert main(["bake", str(blend), "--out", str(out), "--substeps", "1", "--pad", "0"]) == 0
    manifest = json.loads((out / "scene.json").read_text())
    ids = sorted(s["id"] for s in manifest["sources"])
    assert len(ids) == 6 and "CarInst.0/Car:0" in ids and sum(i.startswith("Scatter/Car#") for i in ids) == 2
    assert "Sign:0" in ids  # once, not again as an instance of itself
    arrays = np.load(out / "scene.npz")
    pos = {s["id"]: arrays["src_pos"][0, s["track"]] for s in manifest["sources"]}
    # collection instance: instancer location + child location - instance offset
    assert np.allclose(pos["CarInst.1/Car:0"], [10, 5, 0.5], atol=1e-5)


def test_instance_limit_keeps_the_closest(tmp_path, sine):
    extra = "s['sfx_settings'] = {'instance_limit': 2}"
    blend = blender(INSTANCES.format(sine=sine, extra=extra, path=str(tmp_path / "lim.blend")), tmp_path, "lim")
    out = tmp_path / "bake"
    assert main(["bake", str(blend), "--out", str(out), "--substeps", "1", "--pad", "0"]) == 0
    manifest = json.loads((out / "scene.json").read_text())
    ids = sorted(s["id"] for s in manifest["sources"])
    assert ids == ["CarInst.0/Car:0", "CarInst.1/Car:0", "Sign:0"]
    assert any("instances of tagged object Car" in w for w in manifest["warnings"])


def test_tags_on_objects_created_by_a_run_script(tmp_path, sine):
    blend = blender(CAMERA + f"""
asset = bpy.data.collections.new("Assets")  # excluded from the view layer: not a source by itself
s.collection.children.link(asset)
lamp = bpy.data.objects.new("AssetLamp", None)
asset.objects.link(lamp)
lamp["sfx"] = [{{"sample": {sine!r}}}]
bpy.context.view_layer.layer_collection.children["Assets"].exclude = True
bpy.ops.wm.save_as_mainfile(filepath={str(tmp_path / 'run.blend')!r})
""", tmp_path, "run")
    tags = tmp_path / "tags.py"
    tags.write_text(f"""
import sys, bpy
sys.path.insert(0, {str(REPO)!r})
from soundstage.blender import tag
coll = bpy.data.collections.new("snd")
bpy.context.scene.collection.children.link(coll)
e = bpy.data.objects.new("snd_horn", None)
e.location = (0, 10, 0)
coll.objects.link(e)
tag.add_sound(e, {sine!r})
""")
    out = tmp_path / "bake"
    assert main(["bake", str(blend), "--run", str(tags), "--out", str(out), "--substeps", "1", "--pad", "0"]) == 0
    ids = [s["id"] for s in json.loads((out / "scene.json").read_text())["sources"]]
    assert ids == ["snd_horn:0"]
