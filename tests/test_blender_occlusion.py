"""Visibility bake (FR-25) in Blender scenes (marker ``blender``)."""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from soundstage.cli import main

from conftest import RATE, rms_db

REPO = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.blender

SCENE = """
import bpy, math, sys
sys.path.insert(0, {repo!r})
from soundstage.blender import tag
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
s = bpy.context.scene
s.frame_start, s.frame_end = 1, 60
cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
s.collection.objects.link(cam)
s.camera = cam
cam.rotation_euler = (math.radians(90), 0, 0)

def box(name, loc, size):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = size
    return o

def emitter(name, keys):
    e = bpy.data.objects.new(name, None)
    s.collection.objects.link(e)
    for f, loc in keys:
        e.location = loc
        e.keyframe_insert("location", frame=f)
    tag.add_sound(e, {sample!r})
    return e

{body}
bpy.ops.wm.save_as_mainfile(filepath={path!r})
"""


def bake(tmp_path: Path, body: str, sine: str) -> tuple[dict, dict]:
    script = tmp_path / "scene.py"
    blend = tmp_path / "scene.blend"
    script.write_text(SCENE.format(repo=str(REPO), sample=sine, body=body, path=str(blend)))
    subprocess.run(["blender", "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(script)],
                   check=True, capture_output=True)
    out = tmp_path / "bake"
    assert main(["bake", str(blend), "--out", str(out), "--substeps", "1", "--pad", "0"]) == 0
    manifest = json.loads((out / "scene.json").read_text())
    arrays = np.load(out / "scene.npz")
    vis = {s["id"]: arrays["src_visibility"][:, s["track"]] for s in manifest["sources"]}
    return manifest, vis


def test_source_moving_behind_a_wall(tmp_path, sine):
    manifest, vis = bake(tmp_path, """
box("Wall", (0, 10, 0), (10, 1, 6))
emitter("Src", [(1, (-20, 20, 0)), (60, (0, 20, 0))])
""", sine)
    v = vis["Src:0"]  # (samples, bands 250/1000/4000)
    assert manifest["occlusion"]["bands_hz"] == [250.0, 1000.0, 4000.0]
    assert v[0].min() == 1.0 and v[-1].max() == 0.0  # in view at the start, behind the wall at the end
    assert manifest["occlusion"]["blockers"]["Src:0"][0][0] == "Wall"  # what blocks it, for the agent
    partly = (v[:, 2] > 0) & (v[:, 2] < 1)
    assert partly.any() and np.all(v[partly, 0] >= v[partly, 2])  # low frequencies bend around the edge


def test_visibility_follows_the_emitted_sound(tmp_path, sine):
    _, vis = bake(tmp_path, """
s.frame_end, s.render.fps = 120, 30
bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
box("Wall", (0, 10, 0), (10, 1, 6))
emitter("Far", [(1, (-400, 343, 0)), (121, (0, 343, 0))])
""", sine)
    # 100 m/s; the line of sight reaches the wall's near face (y = 9.5) at x = -180.5 m (t = 2.195 s);
    # that sound, 387.6 m away, is heard 1.130 s later, at 3.325 s (visibility every 0.1 s).
    # Visibility with source and listener at the same instant would close at 2.2 s.
    t = (np.load(tmp_path / "bake" / "scene.npz")["vis_frames"] - 1) / 30
    closed = t[vis["Far:0"][:, 2] == 0.0][0]
    assert 3.3 <= closed <= 3.5


def test_own_box_and_cockpit_do_not_occlude(tmp_path, sine):
    _, vis = bake(tmp_path, """
box("CarBody", (0, 20, 0), (4, 2, 1.5))
emitter("Engine", [(1, (0, 20, 0)), (60, (0, 20, 0))])
box("Cockpit", (0, 0, 0), (3, 3, 3))
box("Pebble", (0, 10, 0), (1, 1, 1))
""", sine)
    assert vis["Engine:0"].min() == 1.0  # inside its own body, camera inside a cockpit, a pebble too small


def test_moving_wall(tmp_path, sine):
    manifest, vis = bake(tmp_path, """
w = box("Door", (-30, 10, 0), (10, 1, 6))
w.keyframe_insert("location", frame=1)
w.location = (0, 10, 0)
w.keyframe_insert("location", frame=60)
emitter("Src", [(1, (0, 20, 0)), (60, (0, 20, 0))])
""", sine)
    assert manifest["occlusion"]["occluders"]["moving"] >= 1
    v = vis["Src:0"]
    assert v[0].min() == 1.0 and v[-1].max() == 0.0


def test_rendered_level_behind_a_wall(tmp_path, sine):
    bake(tmp_path, """
box("Wall", (0, 10, 0), (10, 1, 6))
emitter("Src", [(1, (0, 20, 0)), (60, (0, 20, 0))])
""", sine)
    level = {}
    for name, sets in (("occluded", []), ("open", ["occlusion_gain_db=0", "occlusion_cutoff_hz=20000"])):
        wav = tmp_path / f"{name}.wav"
        args = ["render", str(tmp_path / "bake" / "scene.json"), "-o", str(wav)]
        assert main(args + [a for s in sets for a in ("--set", s)]) == 0
        audio, _ = sf.read(wav)
        level[name] = rms_db(audio[RATE // 2: RATE])
    # 1 kHz behind the wall: -12 dB broadband (250 Hz band) and the one-pole from the upper bands
    # (cutoff 1528 Hz): -12.12 - 1.54 = -13.66 dB; the "open" transmission is flat within 0.01 dB
    assert level["occluded"] - level["open"] == pytest.approx(-13.67, abs=0.3)


def test_moving_collection_instance_occludes(tmp_path, sine):
    manifest, vis = bake(tmp_path, """
w = box("DoorAsset", (0, 0, 0), (10, 1, 6))
asset = bpy.data.collections.new("Door")
for c in list(w.users_collection):
    c.objects.unlink(w)
asset.objects.link(w)
e = bpy.data.objects.new("DoorInst", None)
e.instance_type = "COLLECTION"; e.instance_collection = asset
s.collection.objects.link(e)
e.location = (-30, 10, 0)
e.keyframe_insert("location", frame=1)
e.location = (0, 10, 0)
e.keyframe_insert("location", frame=60)
emitter("Src", [(1, (0, 20, 0)), (60, (0, 20, 0))])
lift = box("Lift", (50, 50, 0), (3, 3, 3))  # a plain moving object as well
lift.keyframe_insert("location", frame=1)
lift.location = (50, 50, 20)
lift.keyframe_insert("location", frame=60)
""", sine)
    assert manifest["occlusion"]["occluders"]["moving"] == 2
    v = vis["Src:0"]
    assert v[0].min() == 1.0 and v[-1].max() == 0.0


def test_ground_reflects_and_a_low_barrier_occludes(tmp_path, sine):
    _, vis = bake(tmp_path, """
cam.location = (0, 0, 1.7)
bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, 0))
emitter("OnGround", [(1, (-5, 60, 1.0)), (60, (-5, 60, 1.0))])
box("Barrier", (20, 30, 0.75), (10, 0.3, 1.5))  # top at 1.5 m, at the path's midpoint
emitter("BehindBarrier", [(1, (40, 60, 3.4)), (60, (40, 60, 3.4))])
""", sine)
    assert vis["OnGround:0"].min() == 1.0  # Fresnel points under the ground are reflected, not blocked
    # the line of sight clears the barrier by 1.05 m: more than the 4 kHz ring radius there (0.88 m),
    # much less than the 250 Hz one (3.5 m)
    v = vis["BehindBarrier:0"][0]
    assert v[2] == 1.0 and v[0] < 1.0


def test_fast_vehicle_is_not_occluded_by_its_own_body(tmp_path, sine):
    _, vis = bake(tmp_path, """
bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
car = box("Car", (0, 0, 0), (4.5, 2, 1.5))
for f, x in ((1, -60.0), (60, 60.0)):  # 60 m/s past the camera, 15 m in front
    car.location = (x, 15, 0)
    car.keyframe_insert("location", frame=f)
tag.add_sound(car, {sample!r})
""".replace("{sample!r}", repr(sine)), sine)
    assert vis["Car:0"].min() == 1.0


MATERIALS = """
def material(kind):
    m = bpy.data.materials.new(kind)
    m.use_nodes = True
    nt = m.node_tree
    out = nt.nodes["Material Output"]
    for n in [n for n in nt.nodes if n != out]:
        nt.nodes.remove(n)
    if kind == "fog":
        nt.links.new(nt.nodes.new("ShaderNodeVolumePrincipled").outputs[0], out.inputs["Volume"])
    elif kind == "beam":
        add = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(nt.nodes.new("ShaderNodeEmission").outputs[0], add.inputs[0])
        nt.links.new(nt.nodes.new("ShaderNodeBsdfTransparent").outputs[0], add.inputs[1])
        nt.links.new(add.outputs[0], out.inputs["Surface"])
    else:
        nt.links.new(nt.nodes.new("ShaderNodeBsdfGlass").outputs[0], out.inputs["Surface"])
    return m

def wall(name, x, kind):
    w = box(name, (x, 10, 0), (6, 1, 6))
    w.data.materials.append(material(kind))
"""


def test_fog_and_light_beams_do_not_occlude_glass_does(tmp_path, sine):
    _, vis = bake(tmp_path, MATERIALS + """
wall("Fog", -20, "fog")
emitter("BehindFog", [(1, (-40, 20, 0)), (60, (-40, 20, 0))])
wall("Beam", 0, "beam")
emitter("BehindBeam", [(1, (0, 20, 0)), (60, (0, 20, 0))])
wall("Glass", 20, "glass")
emitter("BehindGlass", [(1, (40, 20, 0)), (60, (40, 20, 0))])
text = bpy.data.objects.new("Sign", bpy.data.curves.new("Sign", "FONT"))
text.data.body = "HOTEL"
text.data.extrude = 0.2
text.location, text.rotation_euler, text.scale = (-8, 10, -2), (math.radians(90), 0, 0), (4, 4, 4)
s.collection.objects.link(text)
emitter("BehindText", [(1, (0, 40, 0)), (60, (0, 40, 0))])
""", sine)
    assert vis["BehindText:0"].min() == 1.0
    assert vis["BehindFog:0"].min() == 1.0 and vis["BehindBeam:0"].min() == 1.0
    assert vis["BehindGlass:0"][:, 2].max() == 0.0  # 4 kHz blocked; the wide 250 Hz zone passes around the 6 m wall


def test_the_cameras_vehicle_does_not_occlude(tmp_path, sine):
    manifest, vis = bake(tmp_path, """
bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
car = box("CameraCar", (0, 0, 0), (2, 5, 1))
for f, y in ((1, 0.0), (60, 60.0)):
    car.location = (0, y, 0)
    car.keyframe_insert("location", frame=f)
cam.parent = car
cam.location = (0, 0, 1.5)  # on the roof, outside the car's box
cam.rotation_euler = (0, 0, 0)  # looking down
emitter("Below", [(1, (0, 30, -20)), (60, (0, 30, -20))])
""", sine)
    assert manifest["occlusion"]["occluders"]["carried"] == 1
    assert vis["Below:0"].min() == 1.0


def test_a_box_around_the_listener_does_not_occlude(tmp_path, sine):
    _, vis = bake(tmp_path, """
box("MergedBlock", (0, 30, 0), (100, 100, 40))  # e.g. many buildings in one mesh, camera inside its box
emitter("Outside", [(1, (0, 150, 0)), (60, (0, 150, 0))])
""", sine)
    assert vis["Outside:0"].min() == 1.0


def test_merged_meshes_occlude_by_their_parts(tmp_path, sine):
    manifest, vis = bake(tmp_path, """
import bmesh
def merged(name, parts):
    bm = bmesh.new()
    for centre, size in parts:
        geom = bmesh.ops.create_cube(bm, size=1.0)["verts"]
        bmesh.ops.scale(bm, vec=size, verts=geom)
        bmesh.ops.translate(bm, vec=centre, verts=geom)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    o = bpy.data.objects.new(name, me)
    s.collection.objects.link(o)
merged("TwoBuildings", [((-15, 20, 0), (20, 10, 30)), ((15, 20, 0), (20, 10, 30))])  # a 10 m street between them
emitter("DownTheStreet", [(1, (0, 60, 0)), (60, (0, 60, 0))])
merged("Brackets", [((10 * math.cos(a), -40 + 10 * math.sin(a), 0), (1, 1, 1)) for a in [k * math.pi / 4 for k in range(8)]])
emitter("ThroughTheRing", [(1, (0, -80, 0)), (60, (0, -80, 0))])
merged("Tower", [((80, 20, 0), (20, 10, 30)), ((80, 13.5, 5), (6, 3, 3)), ((80, 13.5, 10), (6, 3, 3))])  # shell, 2 balconies
""", sine)
    assert vis["DownTheStreet:0"][:, 2].min() == 1.0  # one box over both buildings would close the street
    assert vis["ThroughTheRing:0"].min() == 1.0  # 1 m brackets are below occluder_min_size
    # the two buildings by their parts, the tower (its shell fills its box) as one box
    assert manifest["occlusion"]["occluders"]["static"] == 3
