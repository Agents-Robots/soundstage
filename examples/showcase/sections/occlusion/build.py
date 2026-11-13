"""Build ``occlusion`` (README.md) in Blender: a row of four houses with a motorbike on the road
behind them, the camera panning with it; a street corner with a busker in the side street, the
camera walking towards the corner. Every source tagged once per pass, with ``occlusion`` off and on.

    blender -b --factory-startup -y --python examples/showcase/sections/occlusion/build.py -- [--out DIR]
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
    BIKE_FADE_OUT_S,
    BUSKER,
    BUSKER_FADE_OUT_S,
    BUSKER_Z,
    CAM_BIKE,
    CORNER_HOUSE,
    CORNER_X,
    ENGINE_Z,
    FADE_IN_S,
    FRONT,
    HOUSE_D,
    HOUSE_H,
    HOUSE_W,
    HOUSES_X,
    LENS_BIKE,
    LENS_BUSKER,
    MARGIN_S,
    OCCLUSION,
    ROAD_Y,
    SECTION,
    SIDE_W,
    TUNE_S,
    TYRES_Z,
    C,
    bike_position,
    busker_open,
    busker_yaw,
    camera_busker,
    house_boxes,
    open_line,
)

from soundstage.blender import tag  # noqa: E402

S = SECTION
FPS = base.story.FPS
BIKE_PASSES = ("bike_off", "bike")
BUSKER_PASSES = ("busker_off", "busker")
OCCLUDERS: list = []
"""The houses' walls and roofs: the only objects that occlude (R2)."""


def house(name: str, width: float, depth: float, height: float, wall: str, seed: int, location, turn_deg: float = 0.0,
          coll=None):
    h = models.house(name, width, depth, height, wall, seed=seed, roof="roof_dark" if seed % 2 else "roof", coll=coll)
    h.location = location
    h.rotation_euler = (0, 0, math.radians(turn_deg))
    OCCLUDERS.extend(o for o in h.children if not o.name.endswith(".windows"))
    return h


# --- motorbike -----------------------------------------------------------------------------------------

def row_set(rnd: random.Random) -> None:
    coll = base.collection("row")
    base.box("occlusion.meadow", (900, 900, 0.2), (0, 0, -0.1), base.surface("grass", 0.95), coll=coll)
    base.box("occlusion.road", (400, 6.0, 0.04), (0, ROAD_Y, 0.02), base.surface("asphalt", 0.9), coll=coll)
    base.box("occlusion.yards", (100, 4.0, 0.03), (0, HOUSE_D + 0.5, 0.015), base.surface("paving", 0.9), coll=coll)
    for i, x in enumerate(HOUSES_X):
        house(f"occlusion.house{i}", HOUSE_W, HOUSE_D, HOUSE_H, f"wall_{1 + i % 5}", seed=i, location=(x, 0, 0),
              coll=coll)
    for i in range(30):  # trees beyond the road: the backdrop in the gaps
        models.tree(f"occlusion.tree{i}", rnd.uniform(8, 12), seed=60 + i, coll=coll).location = (
            -120 + 8.5 * i + rnd.uniform(-2, 2), ROAD_Y + rnd.uniform(9, 22), 0)
    for i in range(8):  # farther houses, out of the line of sight
        house(f"occlusion.far{i}", rnd.choice((10, 12)), 8, rnd.choice((7, 9)), f"wall_{1 + (i + 2) % 5}", seed=20 + i,
              location=(-140 + 40 * i, ROAD_Y + 40 + rnd.uniform(0, 10), 0), coll=coll)


def ride(bike) -> None:
    """The motorbike along the road in each bike pass (heading +X), its wheels turning; at the start
    before."""
    bike.rotation_euler = (0, 0, math.radians(90))  # the model faces -Y
    span = (S.window(BIKE_PASSES[0]).frames - 1) / FPS  # to the last frame: the next pass keys the one after
    start, end = (Vector(bike_position(t)) for t in (0.0, span))
    runs = [[(S.window(k).first, start), (S.window(k).last, end)] for k in BIKE_PASSES]
    base.runs(bike, "location", [[(f, (p.x, p.y, models.VEHICLE_Z)) for f, p in run] for run in runs])
    for hub in [o for o in bike.children if ".wheel" in o.name]:
        turn = (end - start).length / hub["radius"]
        base.runs(hub, "rotation_euler", [[(run[0][0], (0, 0, 0)), (run[1][0], (turn, 0, 0))] for run in runs])


def pan(cam, k: str) -> None:
    """The camera of pass k turns with the motorbike (R3): aimed at it on every frame (from frame 1
    for the first pass, under the title page)."""
    w = S.window(k)
    for f in range(1 if k == BIKE_PASSES[0] else w.first, w.last + 1):
        x, y, z = bike_position(max(0, f - w.first) / FPS)
        rot = (Vector((x, y, z + 0.3)) - Vector(CAM_BIKE)).to_track_quat("-Z", "Y").to_euler()
        base.key(cam, "rotation_euler", f, tuple(rot), "LINEAR")


# --- busker --------------------------------------------------------------------------------------------

def corner_set(rnd: random.Random) -> None:
    """Main street along X, the side street to the north at x 0 to 6 (relative to CORNER_X)."""
    coll = base.collection("corner")
    X = CORNER_X
    base.box("occlusion.corner.ground", (400, 400, 0.2), (X, 0, -0.1), base.surface("grass", 0.95), coll=coll)
    base.box("occlusion.corner.road", (200, 11.0, 0.04), (X, 0, 0.02), base.surface("asphalt", 0.9), coll=coll)
    for side in (-1, 1):
        base.box(f"occlusion.corner.pavement{side}", (200, 3.5, 0.2), (X, side * 7.25, 0.0),
                 base.surface("pavement", 0.9), coll=coll)
    base.box("occlusion.corner.side", (SIDE_W, 60, 0.21), (X + SIDE_W / 2, FRONT + 30, 0.0), base.surface("paving", 0.9),
             coll=coll)
    walls = ["wall_1", "wall_2", "wall_3", "wall_4", "wall_5"]
    x0, x1, y0, y1 = CORNER_HOUSE[0], CORNER_HOUSE[2], CORNER_HOUSE[1], CORNER_HOUSE[3]
    house("occlusion.corner.house", x1 - x0, y1 - y0, 10.5, "wall_3", 1, (X + (x0 + x1) / 2, y0, 0), coll=coll)
    x = x0
    for i in range(5):  # on to the west, the north side
        w = rnd.choice((10, 12, 14))
        house(f"occlusion.corner.n{i}", w, 12, rnd.choice((9, 10.5, 12)), walls[i % 5], 10 + i, (X + x - w / 2, FRONT, 0),
              coll=coll)
        x -= w
    x = SIDE_W
    for i in range(5):  # east of the side street
        w = rnd.choice((10, 12, 14))
        house(f"occlusion.corner.e{i}", w, 14 if i == 0 else 12, rnd.choice((9, 10.5, 12)), walls[(i + 2) % 5], 20 + i,
              (X + x + w / 2, FRONT, 0), coll=coll)
        x += w
    x = -70.0
    for i in range(11):  # the south side, facing north
        w = rnd.choice((10, 12, 14))
        house(f"occlusion.corner.s{i}", w, 12, rnd.choice((9, 10.5, 12)), walls[(i + 4) % 5], 30 + i,
              (X + x + w / 2, -FRONT, 0), 180.0, coll=coll)
        x += w
    for i, (yb, d) in enumerate(((FRONT + 14, 12), (FRONT + 26, 12), (FRONT + 38, 14))):  # along the side street
        if i:  # the corner house covers the first stretch on the west side
            house(f"occlusion.corner.sw{i}", d, 12, 10.5, walls[(i + 1) % 5], 40 + i, (X, yb + d / 2, 0), -90.0, coll=coll)
        house(f"occlusion.corner.se{i}", d, 12, 10.5, walls[(i + 3) % 5], 50 + i, (X + SIDE_W, yb + 2 + d / 2, 0), 90.0,
              coll=coll)
    for i in range(6):
        lamp = models.street_lamp(f"occlusion.corner.lamp{i}", False, facing_deg=180 if i % 2 else 0, coll=coll)
        lamp.location = (X - 40 + 16 * i + (8 if i % 2 else 0), 5.9 if i % 2 == 0 else -5.9, 0)


def walk_camera(cam, k: str) -> None:
    w = S.window(k)
    for f in range(w.first, w.last + 1):
        t = (f - w.first) / FPS
        x, y, z = camera_busker(t)
        base.key(cam, "location", f, (CORNER_X + x, y, z + 0.03 * math.sin(2 * math.pi * t / 0.55)))
        base.key(cam, "rotation_euler", f, base.aim(None, busker_yaw(t), 1.5 if t > 4.0 else -1.0))


# --- sounds --------------------------------------------------------------------------------------------

def sounds(bike, player, bed_anchor) -> None:
    engine = base.empty("occlusion.bike.engine", (0, 0, ENGINE_Z - models.VEHICLE_Z), bike)
    tyres = base.empty("occlusion.bike.tyres", (0, 0, TYRES_Z - models.VEHICLE_Z), bike)
    for k in BIKE_PASSES:
        w = S.window(k)
        far = math.dist(bike_position(9.0), CAM_BIKE)
        end = w.last + 1 - (BIKE_FADE_OUT_S + far / C + MARGIN_S) * FPS
        common = dict(frame=w.first, end_frame=end, fade_in=FADE_IN_S, fade_out=BIKE_FADE_OUT_S, loop_phase=0.0,
                      loop_crossfade=0.0, ref_distance=10.0, occlusion=OCCLUSION[k], group="vehicles")
        tag.add_sound(engine, "car_engine.wav", id=S.source_id(k, "bike_engine"), pitch=1.4, gain_db=3.0, **common)
        tag.add_sound(tyres, "tyre_noise.wav", id=S.source_id(k, "bike_tyres"), gain_db=-5.0, **common)
        tag.add_sound(engine, "noise_pink.wav", id=S.probe_id(k, "noise"), **{**common, "group": "probe"})
    mouth = base.empty("occlusion.busker.mouth", (0, -0.3, BUSKER_Z), player)
    for k in BUSKER_PASSES:
        w = S.window(k)
        common = dict(frame=w.first, end_frame=w.at(TUNE_S), fade_in=0.05, fade_out=BUSKER_FADE_OUT_S, loop_phase=0.0,
                      loop_crossfade=0.0)
        tag.add_sound(mouth, "accordion_loop.wav", id=S.source_id(k, "busker"), ref_distance=4.0,
                      occlusion=OCCLUSION[k], group="music", **common)
        tag.add_sound(mouth, "noise_pink.wav", id=S.probe_id(k, "noise"), ref_distance=4.0, occlusion=OCCLUSION[k],
                      group="probe", **common)
        tag.add_sound(bed_anchor, "town_bed.wav", id=S.source_id(k, "bed"), spatial=False, gain_db=-24.0, group="bed",
                      **common)


# --- overlays ------------------------------------------------------------------------------------------

def open_runs(frames: range, is_open) -> list[tuple[int, int]]:
    runs = []
    for f in frames:
        if is_open(f):
            if runs and runs[-1][1] == f - 1:
                runs[-1] = (runs[-1][0], f)
            else:
                runs.append((f, f))
    return runs


def bike_map(cam, k: str) -> None:
    w = S.window(k)
    listener, source = [], []
    for f in range(w.first, w.last + 1):
        x, y, _ = bike_position((f - w.first) / FPS)
        listener.append((f, CAM_BIKE[0], CAM_BIKE[1]))
        source.append((f, x, y))
    opened = open_runs(range(w.first, w.last + 1),
                       lambda f: open_line(CAM_BIKE, bike_position((f - w.first) / FPS), house_boxes()))
    overlay.sight_map(cam, f"occlusion.{k}", (w.first, w.last), (-56.0, -48.0, 56.0, 14.0), house_boxes(), listener,
                      source, opened, width=0.24)


def busker_map(cam, k: str) -> None:
    w = S.window(k)
    listener, source = [], []
    for f in range(w.first, w.last + 1):
        x, y, _ = camera_busker((f - w.first) / FPS)
        listener.append((f, x, y))
        source.append((f, BUSKER[0], BUSKER[1]))
    opened = open_runs(range(w.first, w.last + 1), lambda f: busker_open((f - w.first) / FPS))
    blocks = [CORNER_HOUSE, (SIDE_W, FRONT, SIDE_W + 12, FRONT + 14)]
    overlay.sight_map(cam, f"occlusion.{k}", (w.first, w.last), (-16.0, -4.0, 16.0, 26.0), blocks, listener, source,
                      opened, width=0.17)


def build(out: Path) -> Path:
    base.new_scene(S)
    base.world("day")
    row_set(random.Random(4))
    corner_set(random.Random(9))
    bike = models.motorbike("occlusion.bike")
    ride(bike)
    player, acc = models.busker("occlusion.busker")
    player.location = (CORNER_X + BUSKER[0], BUSKER[1], 0)
    for k in BUSKER_PASSES:
        w = S.window(k)
        models.play_accordion(acc, (w.first, w.at(TUNE_S)))
    bed_anchor = base.empty("occlusion.bed", (CORNER_X, 0, 2))
    sounds(bike, player, bed_anchor)
    for o in bpy.data.objects:  # R2: only the houses occlude
        if o.type == "MESH":
            o["sfx_occluder"] = o in OCCLUDERS

    cams = {}
    for k in BIKE_PASSES:  # a camera per pass: the restart of a pass is a cut, not a jump of one camera
        cams[k] = base.camera(f"occlusion.cam_{k}", CAM_BIKE, target=bike_position(0.0), lens=LENS_BIKE)
        pan(cams[k], k)
    for k in BUSKER_PASSES:
        x, y, z = camera_busker(0.0)
        cams[k] = base.camera(f"occlusion.cam_{k}", (CORNER_X + x, y, z), lens=LENS_BUSKER,
                              rotation=base.aim(None, busker_yaw(0.0)))
        walk_camera(cams[k], k)

    # --- overlays ----------------------------------------------------------------------------------
    w = S.windows
    first = cams[BIKE_PASSES[0]]
    overlay.title_page(first, S, S.title_window, len(S.passes))
    overlay.fade_black(first, "occlusion.in", (1, 9), None, (1, 9))
    for j, p in enumerate(S.passes):
        cam = cams[p.key]
        overlay.section_tag(cam, cam.name, S.title, [(w[p.key].first, w[p.key].last)])
        overlay.lower_third(cam, f"occlusion.{p.key}", p, j, len(S.passes), w[p.key])
        (bike_map if p.key in BIKE_PASSES else busker_map)(cam, p.key)
    last = w["busker"].last
    overlay.fade_black(cams["busker"], "occlusion.out", None, (last - 8, last), (last - 8, last))
    return base.finish(S, [(1, first)] + [(w[k].first, cams[k]) for k in S.windows if k != BIKE_PASSES[0]], out)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(ap.parse_args(argv).out))
