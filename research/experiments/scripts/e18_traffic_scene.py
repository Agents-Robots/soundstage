"""E18 benchmark scene: flying-car traffic in a canyon, built inside Blender by ``soundstage bake --run``.

Two rows of towers along +X (the occluders), lanes of flying cars at several heights between them
(cars on the -Y side fly +X, on the +Y side -X), and a camera flying down the middle at 30 m/s,
between the lane heights, looking ahead. Every car is an Empty instancing a small car collection,
keyed linearly with a Cycles modifier: it flies its lane from one end of the canyon to the other
and jumps back (a teleport), as traffic is usually animated. Each car carries one engine hum with
its own pitch. Parameters from environment variables:

    E18_CARS       number of cars (default 1000)
    E18_SECONDS    shot length in seconds at 30 fps (default 60)
    E18_SETTINGS   JSON object of scene settings (``sfx_settings``)
    E18_CLUTTER    number of static instanced boxes on the canyon walls (balconies, default 0):
                   geometry-nodes instances of one 3 m box, as a city's façade details

Seeded: the same cars for a given number. Samples from ``samples/`` (``tools/make_test_samples.py``).
Logs ``e18 built_at <unix time>`` when building is done, so the runner can separate build and bake.
"""

import json
import math
import os
import random
import sys
import time
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from soundstage.blender import tag  # noqa: E402
from soundstage.blender.util import log  # noqa: E402

N = int(os.environ.get("E18_CARS", 1000))
SECONDS = float(os.environ.get("E18_SECONDS", 60))
SETTINGS = json.loads(os.environ.get("E18_SETTINGS", "{}"))
CLUTTER = int(os.environ.get("E18_CLUTTER", 0))
FPS = 30
HUM = REPO / "samples" / "engine_hum.wav"
LENGTH = 3000.0  # canyon and lanes from x = -LENGTH/2 to +LENGTH/2
LANES_Y = (-55.0, -35.0, -15.0, 15.0, 35.0, 55.0)
LANES_Z = (40.0, 65.0, 105.0, 130.0)  # the camera flies at 85 m, between them
CAMERA_SPEED = 30.0

t0 = time.time()
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
scene = bpy.context.scene
scene.render.fps, scene.render.fps_base = FPS, 1.0
frame_end = int(round(SECONDS * FPS))
scene.frame_start, scene.frame_end = 1, frame_end
scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
scene["sfx_settings"] = SETTINGS
rng = random.Random(18)

box = bpy.data.meshes.new("box")
box.from_pydata([(x, y, z) for z in (0, 1) for y in (-0.5, 0.5) for x in (-0.5, 0.5)], [],
                [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])

# towers: two rows along the canyon, 30-60 m wide, 120-400 m tall, starting at |y| = 80
towers = bpy.data.collections.new("Towers")
scene.collection.children.link(towers)
for side in (-1, 1):
    x = -LENGTH / 2
    while x < LENGTH / 2:
        w = rng.uniform(30, 60)
        t = bpy.data.objects.new(f"Tower{side}_{int(x)}", box)
        t.location = (x + w / 2, side * (80 + w / 2), -50)
        t.scale = (w, w, rng.uniform(170, 450))
        towers.objects.link(t)
        x += w + rng.uniform(5, 25)

# clutter: balconies on both canyon walls, instanced by geometry nodes from one box on a grid of points
if CLUTTER:
    rows = 100
    per_row = max(1, CLUTTER // (2 * rows))
    pts = [(-LENGTH / 2 + (k + 0.5) * LENGTH / per_row, side * 78.0, 5.0 + 3.0 * r)
           for side in (-1, 1) for r in range(rows) for k in range(per_row)]
    grid = bpy.data.meshes.new("balcony_points")
    grid.from_pydata(pts, [], [])
    holder = bpy.data.objects.new("Balconies", grid)
    scene.collection.objects.link(holder)
    balcony = bpy.data.objects.new("Balcony", box)
    balcony.location = (0.0, 0.0, -200.0)  # the instanced original, out of the way
    scene.collection.objects.link(balcony)
    ng = bpy.data.node_groups.new("balconies", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n_in, n_out = ng.nodes.new("NodeGroupInput"), ng.nodes.new("NodeGroupOutput")
    on_points, info = ng.nodes.new("GeometryNodeInstanceOnPoints"), ng.nodes.new("GeometryNodeObjectInfo")
    info.inputs["Object"].default_value = balcony
    info.inputs["As Instance"].default_value = True
    on_points.inputs["Scale"].default_value = (3.0, 3.0, 3.0)  # the box is 1 m; occluders start at 2 m
    ng.links.new(n_in.outputs[0], on_points.inputs["Points"])
    ng.links.new(info.outputs["Geometry"], on_points.inputs["Instance"])
    ng.links.new(on_points.outputs["Instances"], n_out.inputs[0])
    holder.modifiers.new("balconies", "NODES").node_group = ng

# the car: a small box in a collection, instanced by every car Empty
car_coll = bpy.data.collections.new("CarModel")
car = bpy.data.objects.new("CarBody", box)
car.scale = (4.5, 2.0, 1.4)
car_coll.objects.link(car)
traffic = bpy.data.collections.new("Traffic")
scene.collection.children.link(traffic)


def linear(obj, cyclic: bool) -> None:
    """Make the object's location keys linear (and repeat them with a Cycles modifier)."""
    from bpy_extras import anim_utils
    ad = obj.animation_data
    for fc in anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot).fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
        if cyclic:
            fc.modifiers.new("CYCLES")


def cyclic_line(obj, x_from: float, x_to: float, y: float, z: float, period_frames: float, phase: float) -> None:
    """Linear keys from x_from to x_to over one period, repeated (Cycles): a jump back every period."""
    f0 = 1 - phase * period_frames
    for frame, x in ((f0, x_from), (f0 + period_frames, x_to)):
        obj.location = (x, y, z)
        obj.keyframe_insert("location", frame=frame)
    linear(obj, cyclic=True)


lane_speed = {(y, z): rng.uniform(45, 75) for y in LANES_Y for z in LANES_Z}
for i in range(N):
    y, z = rng.choice(LANES_Y), rng.choice(LANES_Z)
    speed = lane_speed[(y, z)] * rng.choice([0.9, 1.0, 1.1])
    sign = 1 if y < 0 else -1
    e = bpy.data.objects.new(f"Car{i:05d}", None)
    e.instance_type, e.instance_collection = "COLLECTION", car_coll
    traffic.objects.link(e)
    period = LENGTH / speed * FPS
    cyclic_line(e, -sign * LENGTH / 2, sign * LENGTH / 2, y + rng.uniform(-2, 2), z + rng.uniform(-2, 2), period,
                rng.random())
    tag.add_sound(e, str(HUM), group="cars", ref_distance=8.0, pitch=round(rng.uniform(0.85, 1.15), 3))

cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
cam.data.lens = 35.0
scene.collection.objects.link(cam)
scene.camera = cam
cam.rotation_euler = (math.radians(90), 0, math.radians(-90))  # looking along +X
start = -CAMERA_SPEED * SECONDS / 2
for frame, x in ((1, start), (frame_end + 1, start + CAMERA_SPEED * SECONDS)):
    cam.location = (x, 0.0, 85.0)
    cam.keyframe_insert("location", frame=frame)
linear(cam, cyclic=False)

log(f"e18 built {N} cars, {len(towers.objects)} towers, {CLUTTER} balconies, {SECONDS:g} s in "
    f"{time.time() - t0:.1f} s")
log(f"e18 built_at {time.time()}")
