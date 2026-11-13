"""Build ``doppler`` (README.md) in Blender: four sets 3 km apart (a country road, a race track, an
airfield, a railway line), an ambulance, a race car and a plane passing static cameras, and a camera
in a train cab passing a level-crossing bell; a pitch gauge keyed from the geometry.

    blender -b --factory-startup -y --python examples/showcase/sections/doppler/build.py -- [--out DIR]
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
from mathutils import Euler, Vector  # noqa: E402
from section import (  # noqa: E402
    BELL_LEAD_S,
    FADE_IN_S,
    FADE_OUT_S,
    GAUGE_MARKS,
    PASSBYS,
    PLANE_SIDE,
    RACE_PITCH,
    SECTION,
    pass_seconds,
    semitones,
)

from soundstage.blender import tag  # noqa: E402

S = SECTION
FPS = base.story.FPS
SETS = {"road": 0.0, "track": 3000.0, "airfield": 6000.0, "rail": 9000.0}
"""X of each set's origin: the point of closest approach (the bell for the railway)."""
PASS_SET = {"siren_off": "road", "siren": "road", "race": "track", "plane": "airfield", "train": "rail"}
CAMERA_YAW = 50.0
"""Roadside cameras look this far towards the approaching vehicle (compass degrees from facing the
road): the far end of the road is in the frame, and the vehicle leaves it just before passing."""


def ground(name: str, x0: float, colour: str = "grass") -> None:
    v, f = base.box_geometry(1800, 1800, 0.2, x0, 0, -0.1)
    base.mesh_object(f"{name}.ground", v, f, base.surface(colour, 0.95))


def strip(name: str, x0: float, length: float, y: float, width: float, material, z: float = 0.02):
    v, f = base.box_geometry(length, width, 0.04, x0, y, z)
    return base.mesh_object(name, v, f, material)


def dashes(name: str, x0: float, x1: float, y: float, step: float, length: float, width: float, material,
           z: float = 0.045):
    verts, faces = [], []
    x = x0
    while x < x1:
        v, f = base.box_geometry(length, width, 0.01, x + length / 2, y, z, offset=len(verts))
        verts += v
        faces += f
        x += step
    return base.mesh_object(name, verts, faces, material)


def trees(name: str, rnd: random.Random, x0: float, xs: tuple[float, float], ys: tuple[float, float], n: int,
          seed: int) -> None:
    for i in range(n):
        models.tree(f"{name}{i}", rnd.uniform(7, 12), seed=seed + i).location = (
            x0 + rnd.uniform(*xs), rnd.uniform(*ys), 0)


def roadside_camera(name: str, x0: float, lateral: float) -> object:
    return base.camera(name, (x0, -lateral, 1.6), lens=24.0, rotation=base.aim(None, CAMERA_YAW, 1.5))


# --- sets ----------------------------------------------------------------------------------------

def road_set(rnd: random.Random):
    x0 = SETS["road"]
    ground("doppler.road", x0)
    strip("doppler.road.asphalt", x0, 1400, 1.6, 6.5, base.surface("asphalt", 0.9))
    for k, y in enumerate((-1.5, 4.7)):
        strip(f"doppler.road.edge{k}", x0, 1400, y, 0.15, base.surface("marking", 0.6), z=0.045)
    dashes("doppler.road.centre", x0 - 700, x0 + 700, 1.6, 12.0, 4.0, 0.15, base.surface("marking", 0.6))
    for k, (cx, cy, sx, sy) in enumerate(((-160, 120, 260, 180), (150, 110, 240, 160), (-40, -120, 300, 160))):
        strip(f"doppler.road.field{k}", x0 + cx, sx, cy, sy, base.surface("field", 0.95), z=0.01)
    trees("doppler.road.tree", rnd, x0, (-260, 260), (12, 30), 40, 0)
    trees("doppler.road.far", rnd, x0, (-500, 500), (200, 320), 50, 100)
    for i in range(60):  # fence posts along the near verge
        base.box(f"doppler.road.post{i}", (0.1, 0.1, 1.0), (x0 - 150 + 5 * i, -3.2, 0.5), base.surface("wood"))
    models.house("doppler.road.farm", 14, 10, 6, "wall_1", seed=1).location = (x0 - 70, 45, 0)
    models.house("doppler.road.barn", 18, 12, 7, "wall_2", seed=2, roof="roof_dark").location = (x0 - 95, 52, 0)
    return roadside_camera("doppler.cam_road", x0, PASSBYS["siren"].lateral)


def track_set(rnd: random.Random):
    x0 = SETS["track"]
    ground("doppler.track", x0)
    strip("doppler.track.asphalt", x0, 1400, 2.0, 14.0, base.surface("asphalt", 0.85))
    for k, y in enumerate((-5.3, 9.3)):
        for colour, phase in (("kerb_red", 0.0), ("white", 2.0)):
            dashes(f"doppler.track.kerb{k}{colour}", x0 - 700 + phase, x0 + 700, y, 4.0, 2.0, 0.6,
                   base.surface(colour, 0.6), z=0.03)
    for i in range(240):  # the armco: posts and two rails
        base.box(f"doppler.track.armco_post{i}", (0.1, 0.1, 0.75), (x0 - 360 + 3 * i, -8.5, 0.375), base.surface("metal"))
    for k, z in enumerate((0.45, 0.7)):
        base.box(f"doppler.track.armco{k}", (720, 0.05, 0.22), (x0, -8.55, z), base.surface("armco", 0.4))
    # the grandstand across the track: six tiers, a roof, spectators
    for i in range(6):
        base.box(f"doppler.track.tier{i}", (120, 2.0, 0.9 * (i + 1)), (x0 + 30, 20 + 2 * i, 0.45 * (i + 1)),
                 base.surface("stone", 0.9))
    base.box("doppler.track.stand_back", (120, 0.5, 10), (x0 + 30, 31.5, 5), base.surface("panel", 0.9))
    base.box("doppler.track.stand_roof", (122, 14, 0.4), (x0 + 30, 25, 10.4), base.surface("metal", 0.6))
    shirts = ["shirt", "jacket", "car_red", "white", "truck_cab", "car_green"]
    for i in range(90):
        tier = rnd.randrange(6)
        fig = models.figure(f"doppler.track.fan{i}", shirt=shirts[i % len(shirts)])
        fig.location = (x0 + 30 + rnd.uniform(-58, 58), 20 + 2 * tier, 0.9 * (tier + 1))
        fig.rotation_euler = (0, 0, math.pi)
    trees("doppler.track.tree", rnd, x0, (-500, 500), (45, 90), 50, 200)
    return roadside_camera("doppler.cam_track", x0, PASSBYS["race"].lateral)


def airfield_set(rnd: random.Random):
    x0 = SETS["airfield"]
    ground("doppler.air", x0)
    strip("doppler.air.runway", x0, 1200, PLANE_SIDE, 30.0, base.surface("runway", 0.85))
    dashes("doppler.air.centre", x0 - 600, x0 + 600, PLANE_SIDE, 50.0, 25.0, 0.9, base.surface("marking", 0.6))
    base.box("doppler.air.hangar", (40, 30, 10), (x0 + 120, 110, 5), base.surface("hangar", 0.6))
    verts = [(-20.5, -15.5, 10), (20.5, -15.5, 10), (20.5, 15.5, 10), (-20.5, 15.5, 10), (-20.5, 0, 15), (20.5, 0, 15)]
    base.mesh_object("doppler.air.hangar_roof", verts, [(0, 1, 5, 4), (2, 3, 4, 5), (0, 4, 3), (1, 2, 5)],
                     base.surface("metal", 0.5), location=(x0 + 120, 110, 0))
    base.box("doppler.air.hangar_door", (30, 0.1, 8), (x0 + 120, 94.9, 4), base.surface("slate", 0.6))
    base.box("doppler.air.tower", (5, 5, 14), (x0 + 190, 95, 7), base.surface("wall_4", 0.8))
    base.box("doppler.air.tower_cab", (7, 7, 3), (x0 + 190, 95, 15.5), base.surface("glass", 0.15))
    base.cylinder("doppler.air.sock_pole", 0.08, 6, (x0 - 40, -25, 3), base.surface("metal"))
    sock = base.cylinder("doppler.air.sock", 0.45, 2.4, (x0 - 38.8, -25, 5.6), base.surface("windsock", 0.6),
                         axis="X", radius_top=0.2)
    sock.rotation_euler = (0, math.radians(8), 0)
    parked = models.plane("doppler.air.parked", paint="white", stripe="truck_cab")
    parked.location, parked.rotation_euler = (x0 + 95, 85, 1.45), (0, 0, math.radians(200))
    trees("doppler.air.tree", rnd, x0, (-600, 600), (160, 260), 40, 300)
    trees("doppler.air.near", rnd, x0, (-600, -60), (-120, -60), 20, 400)
    return base.camera("doppler.cam_air", (x0, 0, 1.6), lens=35.0, rotation=(0, 0, 0))


def rail_set(rnd: random.Random):
    x0 = SETS["rail"]
    ground("doppler.rail", x0)
    cross = models.crossing("doppler.rail.crossing", bell_y=-PASSBYS["train"].lateral)
    bell_local = next(o for o in cross.children if o.name == "doppler.rail.crossing.bell").location.copy()
    cross.location = (x0 - bell_local.x, 0, 0)  # the bell at the set's origin x
    models.track("doppler.rail.track", x0 - 600, x0 + 600)
    for i in range(24):  # overhead-line poles on the left
        base.box(f"doppler.rail.pole{i}", (0.25, 0.25, 7.5), (x0 - 575 + 50 * i, 3.6, 3.75), base.surface("metal"))
        base.box(f"doppler.rail.arm{i}", (0.15, 3.2, 0.15), (x0 - 575 + 50 * i, 2.1, 7.2), base.surface("metal"))
    base.box("doppler.rail.wire", (1200, 0.03, 0.03), (x0, 0.6, 6.9), base.surface("metal"))
    for k, (cx, cy, sx, sy) in enumerate(((-150, -90, 280, 150), (170, -110, 260, 170), (0, 120, 400, 180))):
        strip(f"doppler.rail.field{k}", x0 + cx, sx, cy, sy, base.surface("field", 0.95), z=0.01)
    models.house("doppler.rail.keeper", 9, 7, 5.5, "wall_3", seed=3).location = (x0 + 18, -16, 0)
    trees("doppler.rail.tree", rnd, x0, (-500, 500), (14, 40), 50, 500)
    trees("doppler.rail.tree_r", rnd, x0, (-500, 500), (-45, -12), 40, 600)
    return cross


# --- action and sound ----------------------------------------------------------------------------

def run(key: str, at_z: float) -> list[tuple[float, Vector]]:
    """(frame, point) of a pass-by along +X of its set at its first and last frame (linear between)."""
    w, p, x0 = S.window(key), PASSBYS[key], SETS[PASS_SET[key]]
    return [(f, Vector((x0 + p.x((f - w.first) / FPS), 0.0, at_z))) for f in (w.first, w.last)]


def rig(name: str, path, children: dict[str, tuple[float, float, float]]):
    """An empty on a pass-by's path (keyed for that pass only) with an empty per emitter."""
    e = base.empty(name)
    base.runs(e, "location", [path])
    return e, {k: base.empty(f"{name}.{k}", v, e) for k, v in children.items()}


def end_frame(key: str) -> float:
    """``end_frame`` of a pass's sources: the fade-out ends where its sound still arrives in time."""
    return S.window(key).first + (PASSBYS[key].end_s(pass_seconds(key)) - FADE_OUT_S) * FPS


def loop(obj, sample: str, sid: str, key: str, frame=None, **kw) -> None:
    tag.add_sound(obj, sample, id=sid, frame=S.window(key).first if frame is None else frame, end_frame=end_frame(key),
                  fade_in=FADE_IN_S if frame is None else 0.0, fade_out=FADE_OUT_S, loop_phase=0.0, loop_crossfade=0.0,
                  **kw)


def check_speed(obj, key: str, speed: float) -> None:
    """R1: the keyed speed, measured from the position on every frame of the pass, within 0.5 %."""
    scene = bpy.context.scene
    w = S.window(key)
    pts = []
    for f in range(w.first, w.last + 1):
        scene.frame_set(f)
        pts.append(obj.matrix_world.translation.copy())
    speeds = [(b - a).length * FPS for a, b in zip(pts, pts[1:])]
    if max(abs(s / speed - 1) for s in speeds) > 0.005:
        raise SystemExit(f"{key}: speed {min(speeds):.2f} to {max(speeds):.2f} m/s, not {speed} (R1)")


def ambulance(amb) -> None:
    w = S.windows
    p = PASSBYS["siren"]
    bar = Vector((0.9, 0, 2.05))  # the light bar from the ambulance's origin, heading +X
    for k in ("siren_off", "siren"):
        path = run(k, p.source_z)
        models.drive(amb, [(f, v - bar) for f, v in path], heading_deg=-90)
        e, em = rig(f"doppler.{k}.rig", path, {"siren": (0, 0, 0), "engine": (0, 0, -1.95), "tyres": (-2.8, 0, -2.45)})
        loop(em["siren"], "siren_two_tone.wav", S.source_id(k, "siren"), k, ref_distance=8.0, group="vehicles")
        loop(em["siren"], "sine_1k.wav", S.probe_id(k, "sine"), k, ref_distance=8.0)
        loop(em["engine"], "car_engine.wav", S.source_id(k, "amb_engine"), k, pitch=0.9, ref_distance=4.0, gain_db=-6.0,
             group="vehicles")
        loop(em["tyres"], "tyre_noise.wav", S.source_id(k, "amb_tyres"), k, ref_distance=4.0, gain_db=-6.0,
             group="vehicles")
        check_speed(e, k, p.speed)
    models.blink(amb, [(w["siren_off"].first, w["siren_off"].last), (w["siren"].first, w["siren"].last)])


def race(car) -> None:
    k, p = "race", PASSBYS["race"]
    path = run(k, p.source_z)
    models.drive(car, [(f, v + Vector((0, 0, 0.1))) for f, v in path], heading_deg=-90)
    e, em = rig("doppler.race.rig", path, {"engine": (0, 0, 0), "tyres": (-1.5, 0, -0.3)})
    loop(em["engine"], "race_engine.wav", S.source_id(k, "engine"), k, pitch=RACE_PITCH, ref_distance=15.0,
         gain_db=3.0, group="vehicles")
    loop(em["engine"], "sine_1k.wav", S.probe_id(k, "sine"), k, ref_distance=15.0)
    loop(em["tyres"], "tyre_noise.wav", S.source_id(k, "tyres"), k, ref_distance=15.0, gain_db=-4.0, group="vehicles")
    check_speed(e, k, p.speed)


def flight(craft, cam) -> None:
    """The plane along +X, 75 m up and PLANE_SIDE to the side; the camera follows it."""
    k, p = "plane", PASSBYS["plane"]
    w = S.window(k)
    path = [(f, v + Vector((0, PLANE_SIDE, 0))) for f, v in run(k, p.source_z)]
    nose = Vector((2.65, 0, 0))  # the propeller from the plane's origin, heading +X
    base.runs(craft, "location", [[(f, v - nose) for f, v in path]])
    craft.rotation_euler = (0, 0, math.radians(90))  # nose (-Y) towards +X
    e, em = rig("doppler.plane.rig", path, {"engine": (0, 0, 0)})
    loop(em["engine"], "prop_plane.wav", S.source_id(k, "engine"), k, ref_distance=80.0, gain_db=5.0, group="vehicles")
    loop(em["engine"], "sine_1k.wav", S.probe_id(k, "sine"), k, ref_distance=80.0)
    check_speed(e, k, p.speed)
    prev = None
    for f in range(w.first, w.last + 1):  # aim at the plane's place on every frame
        target = Vector((SETS["airfield"] + p.x((f - w.first) / FPS), PLANE_SIDE, p.source_z))
        rot = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
        if prev is not None:
            rot.make_compatible(prev)
        prev = rot
        base.key(cam, "rotation_euler", f, Euler(rot), "LINEAR")


def train(cross) -> tuple[object, object]:
    """The train with the cab and the camera, along +X past the crossing; the bell rings."""
    k, p = "train", PASSBYS["train"]
    w = S.window(k)
    loco = base.empty("doppler.train")
    path = run(k, p.camera_z)
    base.runs(loco, "location", [path])
    models.train_cab("doppler.train.cab").parent = loco
    cam = base.camera("doppler.cam_cab", (0, 0, 0), lens=24.0, rotation=base.aim(None, -90, -2.0))
    cam.parent = loco
    roll = base.empty("doppler.train.roll", (-4.0, 0, -2.0), loco)
    tag.add_sound(roll, "train_roll.wav", id=S.source_id(k, "roll"), frame=w.first, end_frame=end_frame(k),
                  fade_in=FADE_IN_S, fade_out=FADE_OUT_S, loop_phase=0.0, loop_crossfade=0.0, ref_distance=3.0, group="vehicles")
    tag.add_sound(roll, "sine_1k.wav", id=S.probe_id(k, "cab"), frame=w.first, end_frame=end_frame(k),
                  fade_in=FADE_IN_S, fade_out=FADE_OUT_S, loop_phase=0.0, loop_crossfade=0.0, ref_distance=3.0)
    bell = next(o for o in cross.children if o.name == "doppler.rail.crossing.bell")
    lead = w.first - BELL_LEAD_S * FPS
    loop(bell, "crossing_bell.wav", S.source_id(k, "bell"), k, frame=lead, ref_distance=6.0, group="bells")
    loop(bell, "sine_1k.wav", S.probe_id(k, "sine"), k, frame=lead, ref_distance=6.0)
    check_speed(loco, k, p.speed)
    models.blink(cross, [(w.first - 60, w.last)], period_s=1.0, on=30.0, off=0.0)
    return loco, cam


def heard_semitones(key: str) -> list[tuple[int, float]]:
    """The pitch gauge: semitones of the rate heard on each frame of the pass (0 without Doppler),
    from the first frame on which the sound has arrived (held at that value before it)."""
    w, p = S.window(key), PASSBYS[key]
    if key == "siren_off":
        return [(w.first, 0.0)]
    t0 = 0.0 if key == "train" else p.heard(0.0)
    end = p.heard(p.end_s(pass_seconds(key)))
    out = []
    for f in range(w.first, w.last + 1):
        t = min(max((f - w.first) / FPS, t0), end)
        out.append((f, semitones(p.rate(t))))
    return out


def build(out: Path) -> Path:
    base.new_scene(S)
    base.world("day")
    rnd = random.Random(11)
    cam_road = road_set(rnd)
    cam_track = track_set(rnd)
    cam_air = airfield_set(rnd)
    cross = rail_set(rnd)

    ambulance(models.ambulance("doppler.ambulance"))
    race(models.race_car("doppler.race_car"))
    flight(models.plane("doppler.plane"), cam_air)
    _, cam_cab = train(cross)

    w = S.windows
    cams = {"siren_off": cam_road, "siren": cam_road, "race": cam_track, "plane": cam_air, "train": cam_cab}
    shots = [(1, cam_road)] + [(w[k].first, cams[k]) for k in ("race", "plane", "train")]

    # --- overlays ----------------------------------------------------------------------------------
    overlay.title_page(cam_road, S, S.title_window, len(S.passes))
    overlay.fade_black(cam_road, "doppler.in", (1, 9), None, (1, 9))
    for cam in (cam_road, cam_track, cam_air, cam_cab):
        mine = [k for k in w if cams[k] is cam]
        overlay.section_tag(cam, cam.name, S.title, [(w[k].first, w[k].last) for k in mine])
    for j, p in enumerate(S.passes):
        cam, win = cams[p.key], w[p.key]
        overlay.lower_third(cam, f"doppler.{p.key}", p, j, len(S.passes), win)
        needle = heard_semitones(p.key)
        ends = () if p.key == "siren_off" else (needle[0][1], needle[-1][1])
        overlay.gauge(cam, f"doppler.{p.key}", list(GAUGE_MARKS), needle, (win.first, win.last), unit="semitones",
                      signed=True, highlights=ends)
    last = w["train"].last
    overlay.fade_black(cam_cab, "doppler.out", None, (last - 8, last), (last - 8, last))
    for o in bpy.data.objects:  # R7: pitch, level and direction only
        if o.type == "MESH":
            o["sfx_occluder"] = False
    return base.finish(S, shots, out)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(ap.parse_args(argv).out))
