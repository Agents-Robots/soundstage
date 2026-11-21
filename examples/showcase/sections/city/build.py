"""Build ``city`` (README.md) in Blender: a city grid at blue hour with 10 000 instanced cars, each
with an engine and tyres, seen from a drone that comes down onto the boulevard's median.

    blender -b --factory-startup -y --python examples/showcase/sections/city/build.py -- [--out DIR]
"""

import argparse
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import bpy  # noqa: E402
from bpy_extras import anim_utils  # noqa: E402
from kit.blender import base, models, overlay  # noqa: E402
from mathutils import Vector  # noqa: E402
from section import (  # noqa: E402
    AVENUE_HALF,
    BANDS,
    BLOCK,
    BOULEVARD_HALF,
    CARS,
    EXTENT,
    GRID,
    PAD_S,
    PASS_S,
    RENDER_CLAIM_MIN,
    SECTION,
    STREET_HALF,
    VARIANTS,
    aim,
    band_end_s,
    band_of,
    drone,
    frame_of,
    min_gap,
    position,
    roads,
    traffic,
)

from soundstage.blender import tag  # noqa: E402

S = SECTION
FPS = base.story.FPS
LENS = 24.0
PROBE_PASS_S = 26.5
"""The probe rides on the westbound boulevard car that passes the camera nearest this time."""
WALLS = ("#4b5361", "#5d5a58", "#3f4a52", "#6a6460")


def hidden_collection(name: str):
    return bpy.data.collections.new(name)


def move_to(root, coll) -> None:
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


# --- materials -----------------------------------------------------------------------------------------

def _math(nt, op: str, a, b=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def facade(name: str, wall: str):
    """Walls with a grid of windows (3.2 m wide bays, 3.6 m storeys) in world coordinates, on the
    vertical faces only; about 40 % of the windows lit, chosen per building by a white noise."""
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    p = nt.nodes["Principled BSDF"]
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    pos = nt.nodes.new("ShaderNodeSeparateXYZ")
    nrm = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], pos.inputs[0])
    nt.links.new(geo.outputs["Normal"], nrm.inputs[0])
    h = _math(nt, "DIVIDE", _math(nt, "ADD", pos.outputs["X"], pos.outputs["Y"]), 3.2)
    v = _math(nt, "DIVIDE", pos.outputs["Z"], 3.6)
    hf, vf = _math(nt, "FRACT", h), _math(nt, "FRACT", v)
    window = _math(nt, "MULTIPLY", _math(nt, "LESS_THAN", hf, 0.62),
                   _math(nt, "MULTIPLY", _math(nt, "GREATER_THAN", vf, 0.3), _math(nt, "LESS_THAN", vf, 0.78)))
    window = _math(nt, "MULTIPLY", window, _math(nt, "LESS_THAN", _math(nt, "ABSOLUTE", nrm.outputs["Z"]), 0.5))
    info = nt.nodes.new("ShaderNodeObjectInfo")
    cell = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(_math(nt, "FLOOR", h), cell.inputs["X"])
    nt.links.new(_math(nt, "FLOOR", v), cell.inputs["Y"])
    nt.links.new(_math(nt, "MULTIPLY", info.outputs["Random"], 1000.0), cell.inputs["Z"])
    noise = nt.nodes.new("ShaderNodeTexWhiteNoise")
    noise.noise_dimensions = "3D"
    nt.links.new(cell.outputs[0], noise.inputs["Vector"])
    lit = _math(nt, "MULTIPLY", window, _math(nt, "GREATER_THAN", noise.outputs["Value"], 0.6))
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    nt.links.new(window, mix.inputs["Factor"])
    mix.inputs["A"].default_value = (*base.linear(wall), 1.0)
    mix.inputs["B"].default_value = base.colour("window")
    nt.links.new(mix.outputs["Result"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.8
    p.inputs["Emission Color"].default_value = base.colour("window_lit")
    nt.links.new(_math(nt, "MULTIPLY", lit, 3.0), p.inputs["Emission Strength"])
    return mat


def lamp_dots(name: str):
    """A strip along a road whose dots glow every 30 m: street lamps seen from above."""
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    p = nt.nodes["Principled BSDF"]
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    pos = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], pos.inputs[0])
    along = _math(nt, "FRACT", _math(nt, "DIVIDE", _math(nt, "ADD", pos.outputs["X"], pos.outputs["Y"]), 30.0))
    dot = _math(nt, "LESS_THAN", along, 0.05)
    p.inputs["Base Color"].default_value = base.colour("asphalt")
    p.inputs["Emission Color"].default_value = base.colour("lamp")
    nt.links.new(_math(nt, "MULTIPLY", dot, 14.0), p.inputs["Emission Strength"])
    return mat


# --- set -----------------------------------------------------------------------------------------------

def ground() -> None:
    base.box("city.ground", (4 * EXTENT, 4 * EXTENT, 0.2), (0, 0, -0.1), base.surface("asphalt", 0.95))
    base.box("city.land", (12000, 12000, 0.2), (0, 0, -0.35), base.surface("hill", 0.95))
    dots = lamp_dots("city.lamps")
    for kind, axis, offset in [("boulevard", "x", 0.0)] + [(k, a, o) for k, a, o in all_roads()]:
        half = {"boulevard": BOULEVARD_HALF, "avenue": AVENUE_HALF, "street": STREET_HALF}[kind] + 1.0
        length = 2 * EXTENT
        for side in (-1, 1):
            c = offset + side * half
            size, loc = ((length, 0.7, 0.04), (0, c, 0.03)) if axis == "x" else ((0.7, length, 0.04), (c, 0, 0.03))
            base.box(f"city.lamps.{axis}{offset:g}.{side}", size, loc, dots)


def all_roads() -> list[tuple[str, str, float]]:
    """Every road, also the streets without traffic (``roads`` lists those with traffic)."""
    out = [("avenue", "x", k * BLOCK) for k in range(-GRID, GRID + 1) if k]
    out += [("street", "y", j * BLOCK) for j in range(-GRID, GRID + 1)]
    return out


def buildings(rnd: random.Random) -> int:
    """Blocks between the roads, two to three lots a side, one building per lot: towers downtown
    (around the boulevard's middle), lower further out. Each building is its own box (an occluder)."""
    mats = [facade(f"city.facade{i}", w) for i, w in enumerate(WALLS)]
    paving = base.surface("pavement", 0.9)
    cube = bpy.data.meshes.new("city.unit_box")
    verts, faces = base.box_geometry(1, 1, 1, 0, 0, 0.5)
    cube.from_pydata(verts, [], faces)
    cube.materials.append(mats[0])
    n = 0
    for j in range(-GRID, GRID):
        x0, x1 = j * BLOCK + STREET_HALF + 2.0, (j + 1) * BLOCK - STREET_HALF - 2.0
        for k in range(-GRID, GRID):
            y0 = k * BLOCK + (BOULEVARD_HALF if k == 0 else AVENUE_HALF) + 2.0
            y1 = (k + 1) * BLOCK - (BOULEVARD_HALF if k + 1 == 0 else AVENUE_HALF) - 2.0
            pave = base.box(f"city.block{j}_{k}", (x1 - x0 + 4, y1 - y0 + 4, 0.15), ((x0 + x1) / 2, (y0 + y1) / 2, 0.075),
                            paving)
            pave["sfx_occluder"] = False
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            r = math.hypot(cx - 150.0, cy - 60.0)
            tall = max(0.0, 1.0 - r / 900.0)
            nx, ny = rnd.choice((2, 3)), rnd.choice((2, 3))
            for a in range(nx):
                for b in range(ny):
                    lx0 = x0 + (x1 - x0) * a / nx
                    lx1 = x0 + (x1 - x0) * (a + 1) / nx
                    ly0 = y0 + (y1 - y0) * b / ny
                    ly1 = y0 + (y1 - y0) * (b + 1) / ny
                    gap = rnd.uniform(2.0, 6.0)
                    height = rnd.uniform(12.0, 30.0) + tall * rnd.uniform(20.0, 120.0)
                    if k in (-1, 0) and abs(cx) < 700:  # the boulevard's canyon
                        height = max(height, rnd.uniform(35.0, 70.0))
                    obj = bpy.data.objects.new(f"city.bldg{n:04d}", cube)
                    obj.material_slots[0].link = "OBJECT"
                    obj.material_slots[0].material = rnd.choice(mats)
                    obj.location = ((lx0 + lx1) / 2, (ly0 + ly1) / 2, 0.0)
                    obj.scale = (lx1 - lx0 - gap, ly1 - ly0 - gap, height)
                    bpy.context.scene.collection.objects.link(obj)
                    n += 1
    return n


def boulevard_dressing() -> None:
    """Near the camera: the raised median, lane lines and lamps on the median every 30 m."""
    base.box("city.median", (2 * EXTENT, 3.0, 0.18), (0, 0, 0.09), base.surface("kerb", 0.8)).__setitem__(
        "sfx_occluder", False)
    for side in (-1, 1):
        for y in (5.5, 9.0):
            for i in range(60):
                x = -300 + i * 12.0
                base.box(f"city.dash{side}_{y}_{i}", (5.0, 0.15, 0.01), (x, side * y, 0.035),
                         base.surface("marking", 0.8)).__setitem__("sfx_occluder", False)
    for i in range(16):
        x = -25.0 + i * 30.0
        lamp = models.street_lamp(f"city.lamp{i}", on=i < 8, facing_deg=90.0 if i % 2 else -90.0)
        lamp.location = (x, 0.0, 0.18)


# --- traffic -------------------------------------------------------------------------------------------

def vehicle_collections(vehicles: list[dict]) -> dict:
    """One collection per variant and distance band: the model with its lights, a pool of light on the
    road ahead and a red glow behind (what shows a car from 600 m), and two tags (engine, tyres at the rear axle), ending
    with the band (``band_end_s``)."""
    out = {}
    pool = base.surface("asphalt", 0.9, "headlight", 0.45)
    tail = base.surface("panel", 0.9, "taillight", 0.8)
    for name, (kind, paint, pitch) in VARIANTS.items():
        for band in range(len(BANDS)):
            coll = hidden_collection(f"city.{name}.{band}")
            coll["sfx_occluder"] = False
            body = f"city.{name}.{band}.body"
            if kind == "car":
                root = models.car(body, paint, lights=True)
                engine, rear, nose = (0, -1.5, 0.5 - models.VEHICLE_Z), (0, 1.35, 0.3 - models.VEHICLE_Z), -2.2
            else:
                root = models.truck(body)
                for o in root.children:
                    if o.name.endswith(".box"):
                        o.active_material = base.surface(paint, 0.6)
                engine, rear, nose = (0, -2.9, 1.0 - models.VEHICLE_Z), (0, 2.4, 0.5 - models.VEHICLE_Z), -4.0
            base.box(f"{body}.pool", (2.2, 6.0, 0.01), (0, nose - 3.1, 0.04 - models.VEHICLE_Z), pool, root)
            base.box(f"{body}.tail_glow", (1.8, 1.4, 0.01), (0, -nose + 0.8, 0.04 - models.VEHICLE_Z), tail, root)
            base.no_occlusion(root)
            move_to(root, coll)
            common = dict(end_frame=frame_of(band_end_s(band, vehicles)), fade_out=BANDS[band][1],
                          loop_phase="random", loop_crossfade=0.0, ref_distance=8.0, group="traffic")
            tag.add_sound(root, "car_engine.wav", offset=engine, pitch=pitch,
                          gain_db=3.0 if kind == "truck" else 0.0, **common)
            tag.add_sound(root, "tyre_noise.wav", offset=rear, **common)
            out[name, band] = coll
    return out


def heading(v: dict) -> float:
    """The model's -Y turned to the direction of travel."""
    if v["axis"] == "x":
        return math.radians(90.0 if v["speed"] > 0 else -90.0)
    return math.radians(180.0 if v["speed"] > 0 else 0.0)


def drive(obj, v: dict) -> None:
    """Constant speed over the whole timeline, extrapolated linearly into the bake's padding (sound
    heard at the pass's start left the far cars before frame 1)."""
    w = S.window("night")
    a, b = Vector(position(v, (1 - w.first) / FPS)), Vector(position(v, PASS_S))
    a.z = b.z = models.VEHICLE_Z
    base.key(obj, "location", 1, tuple(a))
    base.key(obj, "location", w.last + 1, tuple(b))
    ad = obj.animation_data
    for fc in anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot).fcurves:
        fc.extrapolation = "LINEAR"


def drive_traffic(vehicles: list[dict], colls) -> None:
    gap = min_gap(vehicles)
    assert gap > 12.0, f"two vehicles closer than {gap:.1f} m"
    for i, v in enumerate(vehicles):
        obj = instancer(f"city.night.v{i:05d}", colls[v["variant"], band_of(v)], position(v, 0.0), heading(v))
        drive(obj, v)


def probe(vehicles: list[dict]) -> dict:
    """A 1 kHz sine on the westbound boulevard car (inner lane) that passes the camera nearest
    ``PROBE_PASS_S``, at its engine, with the tags' settings (S4)."""
    cam_x = drone(PASS_S)[0]
    lane = [v for v in vehicles if v["road"] == "boulevard" and v["speed"] < 0 and abs(v["across"] - 3.75) < 0.01]
    pick = min(lane, key=lambda v: abs((cam_x - v["along0"]) / v["speed"] - PROBE_PASS_S))
    coll = hidden_collection("city.probe")
    em = base.empty("city.probe.engine", (0, -1.5, 0.5 - models.VEHICLE_Z))
    move_to(em, coll)
    tag.add_sound(em, "sine_1k.wav", ref_distance=8.0, loop_crossfade=0.0, end_frame=frame_of(PASS_S - 1.0),
                  fade_out=0.3, group="probe")
    obj = instancer("city.probe.night.car", coll, position(pick, 0.0), heading(pick))
    drive(obj, pick)
    return pick


# --- camera and overlays -------------------------------------------------------------------------------

def clear_of_buildings(cam_path: list[Vector], margin: float = 3.0) -> None:
    """Stop the build if the camera comes within ``margin`` of a building's box."""
    boxes = []
    for o in bpy.data.objects:
        if o.name.startswith("city.bldg"):
            (x, y, _), (sx, sy, sz) = o.location, o.scale
            boxes.append((x - sx / 2 - margin, x + sx / 2 + margin, y - sy / 2 - margin, y + sy / 2 + margin, sz + margin))
    for f, p in enumerate(cam_path, 1):
        for x0, x1, y0, y1, top in boxes:
            assert not (x0 < p.x < x1 and y0 < p.y < y1 and p.z < top), f"the camera enters a building at frame {f}"


def drone_camera():
    w = S.window("night")
    cam = base.camera("city.cam", drone(0.0), lens=LENS, rotation=(0, 0, 0))
    cam.data.clip_end = 8000.0
    for f in range(1, w.last + 1):
        t = max(0.0, (f - w.first) / FPS)
        loc = Vector(drone(t))
        base.key(cam, "location", f, tuple(loc))
        base.key(cam, "rotation_euler", f, tuple((Vector(aim(t)) - loc).to_track_quat("-Z", "Y").to_euler()))
    return cam


def build(out: Path) -> Path:
    base.new_scene(S)
    base.world("dusk")
    bpy.context.scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.45
    rnd = random.Random(23)
    ground()
    n_buildings = buildings(rnd)
    boulevard_dressing()
    vehicles = traffic()
    drive_traffic(vehicles, vehicle_collections(vehicles))
    pick = probe(vehicles)
    w = S.window("night")
    cam = drone_camera()
    clear_of_buildings([Vector(drone(max(0.0, (f - w.first) / FPS))) for f in range(1, w.last + 1)])
    print(f"city: {n_buildings} buildings, {len(vehicles)} vehicles, {len(roads())} roads with traffic; probe on "
          f"{pick['variant']} at {pick['speed'] * 3.6:.0f} km/h")

    overlay.title_page(cam, S, S.title_window, len(S.passes), card=0.97)  # over the lit city
    overlay.fade_black(cam, "city.in", (1, 9), None, (1, 9))
    overlay.section_tag(cam, "city.night", S.title, [(w.first, w.last)])
    overlay.lower_third(cam, "city.night", S.passes[0], 0, 1, w)
    overlay.readout(cam, "city.count", [(f"{CARS:,} cars".replace(",", " "), (w.first, w.last))], cap=0.035)
    overlay.callout(cam, "city.time", f"Sound rendered in under {RENDER_CLAIM_MIN} minutes on one 16-core CPU",
                    (round(frame_of(20.0)), round(frame_of(28.5))), top=0.13)
    overlay.fade_black(cam, "city.out", None, (w.last - 8, w.last), (w.last - 8, w.last))
    return base.finish(S, [(1, cam)], out, settings={"instance_limit": 0, "pad_seconds": PAD_S})


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(ap.parse_args(argv).out))
