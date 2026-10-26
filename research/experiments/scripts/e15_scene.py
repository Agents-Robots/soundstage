"""E15 benchmark scene, built inside Blender by ``soundstage bake --run`` (or ``scan --run``).

A city block grid with a camera flying down a street, and N tagged sound sources. Parameters come
from environment variables, so one script serves every benchmark case:

    E15_SOURCES     number of sources (default 30)
    E15_KIND        objects | collection | nodes (default objects): tags on animated objects, on an
                    object inside collection instances (one empty per source), or on an object
                    instanced by geometry nodes (one point per source, moved by the node tree)
    E15_BUILDINGS   number of buildings (default 200); each comes with four small props (0.5-3 m)
    E15_SECONDS     shot length in seconds at 30 fps (default 60)
    E15_SETTINGS    JSON object of scene settings (``sfx_settings``), e.g. {"substeps": 8}
    E15_TAG         JSON object of tag keys added to every source, e.g. {"occlusion": false}

Source mix (seeded, the same for a given N): 60 % moving loops at 5-40 m/s, 20 % static loops,
20 % one-shots with a trigger every 3-6 s (half of them moving). Four groups. Samples from
``samples/`` (``tools/make_test_samples.py``). Logs ``e15 built ... in X s`` and the time at
which building finished (``e15 built_at <unix time>``) so the runner can separate build and bake.
"""

import json
import math
import os
import random
import sys
import time
from pathlib import Path

import bpy

t0 = time.time()
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from soundstage.blender import tag  # noqa: E402
from soundstage.blender.util import log  # noqa: E402

N = int(os.environ.get("E15_SOURCES", 30))
KIND = os.environ.get("E15_KIND", "objects")
BUILDINGS = int(os.environ.get("E15_BUILDINGS", 200))
SECONDS = float(os.environ.get("E15_SECONDS", 60))
SETTINGS = json.loads(os.environ.get("E15_SETTINGS", "{}"))
TAG = json.loads(os.environ.get("E15_TAG", "{}"))
FPS = 30
SAMPLES = REPO / "samples"
LOOPS = ["engine_hum.wav", "noise_pink.wav", "sine_1k.wav"]
SHOTS = ["impact.wav", "whoosh.wav", "click.wav"]
GROUPS = ["traffic", "machines", "voices", "impacts"]
BLOCK, STREET = 40.0, 20.0  # block pitch and street width (m)

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
scene = bpy.context.scene
scene.render.fps, scene.render.fps_base = FPS, 1.0
frame_end = int(round(SECONDS * FPS))
scene.frame_start, scene.frame_end = 1, frame_end
rng = random.Random(15)


def linear_keys(obj, keys, cyclic: bool = True) -> None:
    for frame, loc in keys:
        obj.location = loc
        obj.keyframe_insert("location", frame=frame)
    from bpy_extras import anim_utils
    ad = obj.animation_data
    for fc in anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot).fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
        if cyclic:
            fc.modifiers.new("CYCLES")


# --- city: buildings on a square grid of blocks, streets between them, props on the pavements ---
side = max(1, math.ceil(math.sqrt(BUILDINGS)))
half = side * BLOCK / 2
box = bpy.data.meshes.new("box")
box.from_pydata([(x, y, z) for z in (0, 1) for y in (-0.5, 0.5) for x in (-0.5, 0.5)], [],
                [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
city = bpy.data.collections.new("City")
scene.collection.children.link(city)
for i in range(BUILDINGS):
    gx, gy = i % side, i // side
    b = bpy.data.objects.new(f"Building{i}", box)
    w = BLOCK - STREET
    b.location = (gx * BLOCK - half + BLOCK / 2, gy * BLOCK - half + BLOCK / 2, 0)
    b.scale = (rng.uniform(0.6, 1.0) * w, rng.uniform(0.6, 1.0) * w, rng.uniform(6, 60))
    city.objects.link(b)
    for k in range(4):
        p = bpy.data.objects.new(f"Prop{i}.{k}", box)
        a = k * math.pi / 2 + rng.uniform(-0.3, 0.3)
        p.location = (b.location.x + math.cos(a) * (w / 2 + 3), b.location.y + math.sin(a) * (w / 2 + 3), 0)
        s = rng.uniform(0.5, 3.0)
        p.scale = (s, s, s)
        city.objects.link(p)
ground = bpy.data.objects.new("Ground", box)
ground.scale = (2 * half + 400, 2 * half + 400, 0.01)
ground.location = (0, 0, -0.01)
scene.collection.objects.link(ground)

# --- camera: down the street along +Y at 15 m/s, 8 m up, looking ahead ---
cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
scene.collection.objects.link(cam)
scene.camera = cam
cam.rotation_euler = (math.radians(85), 0, 0)
street_x = -half + BLOCK * (side // 2)
linear_keys(cam, [(1, (street_x, -half - 50, 8.0)), (frame_end + 1, (street_x, -half - 50 + 15 * SECONDS, 8.0))],
            cyclic=False)

# --- sources ---
kinds = []
for i in range(N):
    r = i % 10
    kinds.append("moving" if r < 6 else "static" if r < 8 else "shot")


def place(i: int) -> tuple[tuple, tuple]:
    """Start and velocity of source i: near the camera's path so that sources pass it."""
    y = rng.uniform(-half - 50, -half - 50 + 15 * SECONDS + 100)
    x = street_x + rng.choice([-1, 1]) * rng.uniform(0, 120)
    z = rng.uniform(0.5, 20)
    speed = rng.uniform(5, 40)
    a = rng.uniform(0, 2 * math.pi)
    return (x, y, z), (speed * math.cos(a), speed * math.sin(a), 0.0)


def entry(i: int) -> dict:
    e = {"group": GROUPS[i % 4], "ref_distance": rng.choice([2.0, 5.0, 10.0])}
    if kinds[i] == "shot":
        period = rng.uniform(3, 6) * FPS
        first = rng.uniform(1, min(period, frame_end))
        e.update(sample=str(SAMPLES / SHOTS[i % 3]), mode="once",
                 frame=[round(first + k * period, 1) for k in range(int((frame_end - first) // period) + 1)])
    else:
        e.update(sample=str(SAMPLES / LOOPS[i % 3]), pitch=round(rng.uniform(0.8, 1.25), 3))
    e.update(TAG)
    return e


starts = [place(i) for i in range(N)]
moving = [kinds[i] == "moving" or (kinds[i] == "shot" and i % 20 == 9) for i in range(N)]
period_s = 20.0  # moving sources repeat a 20 s straight pass (cyclic keys)

if KIND == "objects":
    for i in range(N):
        o = bpy.data.objects.new(f"Src{i}", None)
        scene.collection.objects.link(o)
        (p, v) = starts[i]
        if moving[i]:
            linear_keys(o, [(1, p), (1 + period_s * FPS, tuple(c + period_s * d for c, d in zip(p, v)))])
        else:
            o.location = p
        tag.add_sound(o, **entry(i))
elif KIND in ("collection", "nodes"):
    # one tagged asset per source kind is not needed: the tag sits on the asset object, so every
    # instance gets the same entries; per-instance variety comes from the asset index
    assets = []
    for i in range(min(N, 10)):  # ten assets cover the source mix (index modulo 10)
        coll = bpy.data.collections.new(f"Asset{i}")
        o = bpy.data.objects.new(f"Emitter{i}", None)
        coll.objects.link(o)
        tag.add_sound(o, **entry(i))
        assets.append(coll)
    if KIND == "collection":
        for i in range(N):
            e = bpy.data.objects.new(f"Inst{i}", None)
            e.instance_type, e.instance_collection = "COLLECTION", assets[i % 10]
            scene.collection.objects.link(e)
            (p, v) = starts[i]
            if moving[i]:
                linear_keys(e, [(1, p), (1 + period_s * FPS, tuple(c + period_s * d for c, d in zip(p, v)))])
            else:
                e.location = p
    else:
        # points carry their asset index and velocity; instances move as position + velocity * (t mod period)
        mesh = bpy.data.meshes.new("pts")
        mesh.from_pydata([starts[i][0] for i in range(N)], [], [])
        vel = mesh.attributes.new("vel", "FLOAT_VECTOR", "POINT")
        idx = mesh.attributes.new("asset", "INT", "POINT")
        for i in range(N):
            vel.data[i].vector = starts[i][1] if moving[i] else (0, 0, 0)
            idx.data[i].value = i % 10
        holder = bpy.data.collections.new("Assets")
        for c in assets:
            holder.children.link(c)
        gn = bpy.data.objects.new("Emitters", mesh)
        scene.collection.objects.link(gn)
        tree = bpy.data.node_groups.new("emitters", "GeometryNodeTree")
        tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        nd, ln = tree.nodes.new, tree.links.new
        nin, nout = nd("NodeGroupInput"), nd("NodeGroupOutput")
        t = nd("GeometryNodeInputSceneTime")
        mod = nd("ShaderNodeMath"); mod.operation = "FLOORED_MODULO"; mod.inputs[1].default_value = period_s
        ln(t.outputs["Seconds"], mod.inputs[0])
        va = nd("GeometryNodeInputNamedAttribute"); va.data_type = "FLOAT_VECTOR"; va.inputs["Name"].default_value = "vel"
        sc = nd("ShaderNodeVectorMath"); sc.operation = "SCALE"
        ln(va.outputs["Attribute"], sc.inputs[0]); ln(mod.outputs[0], sc.inputs["Scale"])
        sp = nd("GeometryNodeSetPosition")
        ln(nin.outputs[0], sp.inputs["Geometry"]); ln(sc.outputs[0], sp.inputs["Offset"])
        ci = nd("GeometryNodeCollectionInfo"); ci.inputs["Collection"].default_value = holder
        ci.inputs["Separate Children"].default_value = True
        ci.inputs["Reset Children"].default_value = True
        ia = nd("GeometryNodeInputNamedAttribute"); ia.data_type = "INT"; ia.inputs["Name"].default_value = "asset"
        iop = nd("GeometryNodeInstanceOnPoints")
        iop.inputs["Pick Instance"].default_value = True
        ln(sp.outputs[0], iop.inputs["Points"]); ln(ci.outputs[0], iop.inputs["Instance"])
        ln(ia.outputs["Attribute"], iop.inputs["Instance Index"])
        ln(iop.outputs[0], nout.inputs[0])
        gn.modifiers.new("GN", "NODES").node_group = tree
else:
    raise SystemExit(f"E15_KIND: unknown kind {KIND!r}")

tag.set_scene_settings(scene, **SETTINGS)
scene.frame_set(1)
log(f"e15 built {N} sources ({KIND}), {BUILDINGS} buildings, {SECONDS:g} s in {time.time() - t0:.2f} s")
log(f"e15 built_at {time.time():.3f}")
