"""Build ``scale`` (README.md) in Blender: a queue of forty cars that are instances of one
collection with one tag, heard with one loop phase and with one each; a motorway of 300 instanced
vehicles under a bridge, seen from a drone.

    blender -b --factory-startup -y --python examples/showcase/sections/scale/build.py -- [--out DIR]
"""

import argparse
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import bpy  # noqa: E402
from kit.blender import base, models, overlay  # noqa: E402
from mathutils import Vector  # noqa: E402
from section import (  # noqa: E402
    BANDS,
    BRIDGE_Z,
    FADE_IN_S,
    IDLE_SECONDS,
    INSTANCE_LIMIT,
    QUEUE,
    QUEUE_END_S,
    QUEUE_ENGINE,
    SECTION,
    VARIANTS,
    band_end_s,
    band_of,
    camera_queue,
    drone,
    loop_phase_s,
    min_gap,
    queue_x,
    traffic,
)

from soundstage.blender import tag  # noqa: E402

S = SECTION
FPS = base.story.FPS
QUEUE_PASSES = ("same", "random")
MOTORWAY_Y = 600.0
"""The motorway set stands 600 m from the queue (along Y), out of earshot of nothing that sounds:
every source belongs to one pass."""
QUEUE_GAIN_DB = -6.0
"""Forty idling engines, the nearest 2.5 m away: as loud as the motorway's reference pass."""
PAINTS = {"car_a": "car_red", "car_b": "car_blue", "car_c": "car_grey", "car_d": "car_green"}


def hidden_collection(name: str):
    """A collection that is instanced but not itself in the scene."""
    return bpy.data.collections.new(name)


def move_to(root, coll) -> None:
    """Move a model built in the scene into ``coll`` (its objects keep their parents)."""
    for o in [root, *root.children_recursive]:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)


def instancer(name: str, coll, location, rotation_z: float = 0.0):
    obj = base.empty(name, location)
    obj.instance_type = "COLLECTION"
    obj.instance_collection = coll
    obj.rotation_euler = (0, 0, rotation_z)
    return obj


def window_tags(k: str) -> dict:
    w = S.window(k)
    return dict(frame=w.first, end_frame=w.at(QUEUE_END_S), fade_in=FADE_IN_S, fade_out=0.3, loop_crossfade=0.0)


# --- queue ---------------------------------------------------------------------------------------------

def queue_set(rnd: random.Random) -> None:
    base.box("scale.queue.field", (3000, 850, 0.2), (100, -125, -0.1), base.surface("field", 0.95))
    base.box("scale.queue.road", (600, 7.0, 0.04), (100, 1.0, 0.02), base.surface("asphalt", 0.9))
    base.box("scale.queue.line", (600, 0.12, 0.01), (100, 1.0, 0.045), base.surface("marking", 0.8))
    for i in range(50):
        models.tree(f"scale.queue.tree{i}", rnd.uniform(7, 11), seed=200 + i).location = (
            -40 + 7 * i + rnd.uniform(-2, 2), rnd.choice((-1, 1)) * rnd.uniform(9, 30), 0)
    visual = hidden_collection("scale.queue_car")
    car = models.car("scale.queue_car.body", "car_blue")
    car.location = (0, 0, models.VEHICLE_Z)
    move_to(car, visual)
    for i in range(QUEUE):
        # the model faces -Y: turned by 90 degrees it faces +X, the front of the queue
        instancer(f"scale.queue.car{i:02d}", visual, (queue_x(i), 0, 0), math.radians(90))
    for k in QUEUE_PASSES:
        for kind, sample in (("engine", "car_idle.wav"), ("probe", "noise_pink.wav")):
            coll = hidden_collection(f"scale.queue_{k}_{kind}")
            em = base.empty(f"scale.queue_{k}.{kind}", QUEUE_ENGINE)
            move_to(em, coll)
            tag.add_sound(em, sample, ref_distance=3.0, loop_phase=0.0 if k == "same" else "random",
                          gain_db=QUEUE_GAIN_DB if kind == "engine" else 0.0,
                          group="cars" if kind == "engine" else "probe", **window_tags(k))
            prefix = f"scale.{k}" if kind == "engine" else f"scale.probe.{k}"
            for i in range(QUEUE):
                instancer(f"{prefix}.q{i:02d}", coll, (queue_x(i), 0, 0))


def queue_marks(cam, k: str) -> None:
    """40 marks at the upper right, one per car, each pulsing once a second at its loop's phase."""
    w = S.window(k)
    hud = base.hud_of(cam)
    layer = overlay.Layer(f"scale.{k}.marks")
    objs = [overlay.rounded(hud, f"scale.{k}.marks.panel", 0.62, 0.05, 0.95, 0.105, 0.008, layer.mat("panel", 0.86),
                            z=0.0015)]
    for i in range(QUEUE):
        phase = 0.0 if k == "same" else loop_phase_s(f"scale.{k}.q{i:02d}/scale.queue_{k}.engine:0", IDLE_SECONDS)
        mover = base.empty(f"scale.{k}.mark{i}", parent=hud)
        x = 0.635 + i * (0.3 / (QUEUE - 1))
        dot = overlay.disc(mover, f"scale.{k}.mark{i}.dot", 0.0, 0.0, 0.0045, layer.mat("accent"), z=0.003)
        mover.location = (overlay.hx(x) - overlay.hx(0.0), overlay.hy(0.0775) - overlay.hy(0.0), 0)
        for f in range(w.first, w.last + 1):
            u = ((f - w.first) / FPS + phase) % 1.0
            base.key(mover, "scale", f, (1.8, 1.8, 1.0) if u < 0.12 else (1.0, 1.0, 1.0), "CONSTANT")
        objs.append(dot)
    overlay.show(objs, [(w.first, w.last)])


# --- motorway ------------------------------------------------------------------------------------------

def motorway_set(rnd: random.Random) -> None:
    y0 = MOTORWAY_Y
    base.box("scale.mw.ground", (5000, 1200, 0.2), (0, y0 + 300, -0.1), base.surface("field", 0.95))
    for side in (-1, 1):
        base.box(f"scale.mw.carriageway{side}", (4200, 8.5, 0.04), (0, y0 + side * 7.25, 0.02),
                 base.surface("asphalt", 0.9))
        for y in (5.5 - 1.75, 5.5 + 1.75, 7.25):
            if y == 7.25:
                base.box(f"scale.mw.lane_line{side}", (4200, 0.15, 0.01), (0, y0 + side * y, 0.045),
                         base.surface("marking", 0.8))
            else:
                base.box(f"scale.mw.edge{side}_{y}", (4200, 0.2, 0.01), (0, y0 + side * y, 0.045),
                         base.surface("marking", 0.8))
    base.box("scale.mw.median", (4200, 2.4, 0.5), (0, y0, 0.25), base.surface("kerb", 0.8))
    # the bridge: a road across the motorway at x = 0
    deck = base.box("scale.mw.bridge", (12, 70, 1.2), (0, y0, BRIDGE_Z), base.surface("stone_light", 0.8))
    deck["sfx_occluder"] = True
    for side in (-1, 1):
        base.box(f"scale.mw.bridge_rail{side}", (0.3, 70, 1.0), (side * 5.8, y0, BRIDGE_Z + 1.1), base.surface("metal"))
        base.box(f"scale.mw.pier{side}", (2.0, 1.4, BRIDGE_Z), (0, y0 + side * 13.5, BRIDGE_Z / 2),
                 base.surface("stone_light", 0.8))
        base.box(f"scale.mw.abutment{side}", (14, 8, BRIDGE_Z), (0, y0 + side * 32, BRIDGE_Z / 2),
                 base.surface("stone_light", 0.8))
    base.box("scale.mw.pier0", (2.0, 1.4, BRIDGE_Z), (0, y0, BRIDGE_Z / 2), base.surface("stone_light", 0.8))
    for i in range(80):
        models.tree(f"scale.mw.tree{i}", rnd.uniform(8, 13), seed=300 + i).location = (
            rnd.uniform(-1500, 1500), y0 + rnd.choice((-1, 1)) * rnd.uniform(25, 120), 0)


def vehicle_collections(vehicles: list[dict]) -> dict:
    """One collection per variant and distance band: the model and its two tags (engine, tyres at the
    rear axle), ending with the band (``band_end_s``)."""
    out = {}
    w = S.window("motorway")
    for name, (kind, pitch, _) in VARIANTS.items():
        for band in range(len(BANDS)):
            coll = hidden_collection(f"scale.{name}.{band}")
            coll["sfx_occluder"] = False  # R4
            body = f"scale.{name}.{band}.body"
            if kind == "car":
                root = models.car(body, PAINTS[name], lights=False)
                engine, rear = (0, -1.5, 0.5 - models.VEHICLE_Z), [0, 1.35, 0.3 - models.VEHICLE_Z]
            else:
                root = models.truck(body)
                if name == "truck_b":
                    for o in root.children:
                        if o.name.endswith(".box"):
                            o.active_material = base.surface("car_red", 0.6)
                engine, rear = (0, -2.9, 1.0 - models.VEHICLE_Z), [0, 2.4, 0.5 - models.VEHICLE_Z]
            move_to(root, coll)
            common = dict(frame=w.first, end_frame=w.at(band_end_s(band, vehicles)), fade_in=FADE_IN_S,
                          fade_out=BANDS[band][1], loop_phase="random", loop_crossfade=0.0, ref_distance=8.0,
                          group="traffic")
            tag.add_sound(root, "car_engine.wav", offset=engine, pitch=pitch,
                          gain_db=3.0 if kind == "truck" else 0.0, **common)
            tag.add_sound(root, "tyre_noise.wav", offset=rear, **common)
            out[name, band] = coll
    return out


def drive_traffic(vehicles: list[dict], colls) -> int:
    gap = min_gap(vehicles)
    assert gap > 12.0, f"two vehicles closer than {gap:.1f} m (R5)"
    w = S.window("motorway")
    for i, v in enumerate(vehicles):
        y = MOTORWAY_Y + v["y"]
        heading = 90.0 if v["speed"] > 0 else -90.0  # the model's -Y turned to +X or -X
        obj = instancer(f"scale.motorway.v{i:03d}", colls[v["variant"], band_of(v)], (v["x0"], y, models.VEHICLE_Z),
                        math.radians(heading))
        a = Vector((v["x0"], y, models.VEHICLE_Z))
        b = a + Vector((v["speed"] * w.seconds, 0, 0))
        base.runs(obj, "location", [[(w.first, a), (w.last + 1, b)]])
    return len(vehicles)


def drone_camera():
    w = S.window("motorway")
    x, y, z = drone(0.0)
    cam = base.camera("scale.cam_motorway", (x, MOTORWAY_Y + y, z), lens=28.0, rotation=(0, 0, 0))
    for f in range(w.first, w.last + 1):
        t = (f - w.first) / FPS
        x, y, z = drone(t)
        loc = Vector((x, MOTORWAY_Y + y, z))
        # looking along the eastbound traffic and down at the road ahead of the bridge
        target = Vector((x + 90.0 + 2.0 * (z - 12.0), MOTORWAY_Y - 2.0, 2.0))
        base.key(cam, "location", f, tuple(loc))
        base.key(cam, "rotation_euler", f, tuple((target - loc).to_track_quat("-Z", "Y").to_euler()))
    return cam


def build(out: Path) -> Path:
    base.new_scene(S)
    base.world("day")
    rnd = random.Random(31)
    queue_set(rnd)
    motorway_set(rnd)
    vehicles = traffic()
    n = drive_traffic(vehicles, vehicle_collections(vehicles))
    for o in bpy.data.objects:  # R4: only the bridge occludes
        if o.type == "MESH" and not o.name.startswith("scale.mw.bridge") and not o.name.startswith("scale.mw.pier"):
            o["sfx_occluder"] = False
    cams = {}
    for k in QUEUE_PASSES:  # a camera per pass: the restart of the walk is a cut
        w = S.window(k)
        cams[k] = base.camera(f"scale.cam_{k}", camera_queue(0.0), rotation=base.aim(None, -90.0, -6.0), lens=24.0)
        for f in range(1 if k == "same" else w.first, w.last + 1):
            base.key(cams[k], "location", f, camera_queue(max(0, f - w.first) / FPS))
    cams["motorway"] = drone_camera()

    # --- overlays ----------------------------------------------------------------------------------
    w = S.windows
    overlay.title_page(cams["same"], S, S.title_window, len(S.passes))
    overlay.fade_black(cams["same"], "scale.in", (1, 9), None, (1, 9))
    for j, p in enumerate(S.passes):
        cam = cams[p.key]
        overlay.section_tag(cam, f"scale.{p.key}", S.title, [(w[p.key].first, w[p.key].last)])
        overlay.lower_third(cam, f"scale.{p.key}", p, j, len(S.passes), w[p.key])
    for k in QUEUE_PASSES:
        queue_marks(cams[k], k)
    overlay.readout(cams["motorway"], "scale.count", [(f"{2 * n} sources", (w["motorway"].first, w["motorway"].last))],
                    cap=0.035)
    last = w["motorway"].last
    overlay.fade_black(cams["motorway"], "scale.out", None, (last - 8, last), (last - 8, last))
    return base.finish(S, [(1, cams["same"]), (w["random"].first, cams["random"]), (w["motorway"].first, cams["motorway"])],
                       out, settings={"instance_limit": INSTANCE_LIMIT})


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(ap.parse_args(argv).out))
