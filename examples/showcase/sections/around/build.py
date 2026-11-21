"""Build ``around`` (README.md) in Blender: a roundabout in a town by day, the camera in the middle of
its island, a scooter circling it at 12 m once per pass; an inset map and the arrival-time difference.

    blender -b --factory-startup -y --python examples/showcase/sections/around/build.py -- [--out DIR]
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
from section import (  # noqa: E402
    CAMERA,
    EMITTER_Z,
    FADE_IN_S,
    FADE_OUT_S,
    LENS,
    MARGIN_S,
    RADIUS,
    SECTION,
    C,
    angle,
    itd_ms,
    position,
)

from soundstage.blender import tag  # noqa: E402

S = SECTION
FPS = base.story.FPS
ROAD = (8.6, 15.4)
"""Inner and outer radius of the ring road (m); the scooter rides in its middle."""


def annulus(name: str, r0: float, r1: float, material, z: float, segments: int = 96):
    verts = []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        verts += [(r0 * math.cos(a), r0 * math.sin(a), z), (r1 * math.cos(a), r1 * math.sin(a), z)]
    faces = [(2 * i, 2 * ((i + 1) % segments), 2 * ((i + 1) % segments) + 1, 2 * i + 1) for i in range(segments)]
    return base.mesh_object(name, verts, faces, material)


def roundabout(rnd: random.Random) -> None:
    v, f = base.box_geometry(600, 600, 0.2, 0, 0, -0.1)
    base.mesh_object("around.ground", v, f, base.surface("grass", 0.95))
    annulus("around.ring", ROAD[0], ROAD[1], base.surface("asphalt", 0.9), 0.02)
    annulus("around.kerb_in", ROAD[0] - 0.25, ROAD[0], base.surface("kerb", 0.8), 0.08)
    annulus("around.kerb_out", ROAD[1], ROAD[1] + 0.25, base.surface("kerb", 0.8), 0.08)
    annulus("around.pavement", ROAD[1] + 0.25, ROAD[1] + 4.0, base.surface("paving", 0.9), 0.1)
    for k, a in enumerate((0, 90, 180, 270)):  # four streets leave the roundabout
        rad = math.radians(a)
        street = base.box(f"around.street{k}", (7.0, 140, 0.04), (0, 0, 0.021), base.surface("asphalt", 0.9))
        street.location = (math.sin(rad) * (ROAD[1] + 70), math.cos(rad) * (ROAD[1] + 70), 0.021)
        street.rotation_euler = (0, 0, -rad)
    for i in range(22):  # low planting on the island
        a, r = rnd.uniform(0, 2 * math.pi), rnd.uniform(4.5, 7.4)  # clear of the camera's foreground
        bush = base.sphere(f"around.bush{i}", rnd.uniform(0.35, 0.6), (r * math.cos(a), r * math.sin(a), 0.2),
                           base.surface("leaf" if i % 2 else "leaf_dark", 0.9), segments=8, rings=6)
        bush.scale = (1.0, 1.0, 0.6)
    for k, a in enumerate((45, 135, 225, 315)):  # houses in the four corners, facing the roundabout
        for j, (off, r) in enumerate(((-17, 34), (0, 31), (17, 34))):
            rad = math.radians(a + off)
            h = models.house(f"around.house{k}{j}", rnd.choice((10, 12, 14)), 10, rnd.choice((7, 9.5, 12)),
                             f"wall_{1 + (k + j) % 5}", seed=10 * k + j)
            h.location = (r * math.sin(rad), r * math.cos(rad), 0)
            h.rotation_euler = (0, 0, -rad + math.pi)
        rad = math.radians(a)
        models.tree(f"around.tree{k}", rnd.uniform(7, 9), seed=k).location = (22 * math.sin(rad), 22 * math.cos(rad), 0)
        models.street_lamp(f"around.lamp{k}", False, facing_deg=-a + 180).location = (
            (ROAD[1] + 1.2) * math.sin(rad), (ROAD[1] + 1.2) * math.cos(rad), 0)


def lap(scooter) -> None:
    """The scooter on its circle on every frame, clockwise seen from above (heading along the
    circle), its wheels turning; the lap starts straight ahead on the first pass's first frame."""
    first = S.window("lap").first
    wheels = [o for o in scooter.children if ".wheel" in o.name]
    for f in range(1, S.frame_end + 1):
        t = (f - first) / FPS
        x, y, _ = position(t)
        base.key(scooter, "location", f, (x, y, models.VEHICLE_Z))
        base.key(scooter, "rotation_euler", f, (0, 0, math.pi / 2 - angle(t)))  # the front (-Y) along the motion
        for hub in wheels:
            base.key(hub, "rotation_euler", f, (RADIUS * angle(t) / hub["radius"], 0, 0))


def sounds(scooter) -> None:
    engine = base.empty("around.scooter.engine", (0, 0, EMITTER_Z - models.VEHICLE_Z), scooter)
    tyres = base.empty("around.scooter.tyres", (0, 0, 0.3 - models.VEHICLE_Z), scooter)
    for k, w in S.windows.items():
        end = w.last + 1 - (FADE_OUT_S + RADIUS / C + MARGIN_S) * FPS
        common = dict(frame=w.first, end_frame=end, fade_in=FADE_IN_S, fade_out=FADE_OUT_S, loop_phase=0.0,
                      loop_crossfade=0.0, ref_distance=RADIUS)
        tag.add_sound(engine, "car_engine.wav", id=S.source_id(k, "engine"), pitch=1.6, group="vehicles", **common)
        tag.add_sound(tyres, "tyre_noise.wav", id=S.source_id(k, "tyres"), gain_db=-6.0, group="vehicles", **common)
        tag.add_sound(engine, "noise_pink.wav", id=S.probe_id(k, "noise"), **common)


def itd_shots(window) -> list[tuple[str, tuple[int, int]]]:
    """The arrival-time difference of the sound heard on each frame (emitted 12 m / c earlier), as
    runs of frames with the same text."""
    first = S.window("lap").first
    runs: list[tuple[str, list[int]]] = []
    for f in range(window.first, window.last + 1):
        body = f"Δt {abs(itd_ms((f - first) / FPS - RADIUS / C)):.2f} ms"
        if runs and runs[-1][0] == body:
            runs[-1][1][1] = f
        else:
            runs.append((body, [f, f]))
    return [(body, (a, b)) for body, (a, b) in runs]


def build(out: Path) -> Path:
    base.new_scene(S)
    base.world("day")
    rnd = random.Random(5)
    roundabout(rnd)
    scooter = models.scooter("around.scooter")
    lap(scooter)
    sounds(scooter)
    cam = base.camera("around.cam", CAMERA, lens=LENS, rotation=base.aim(None, 0.0, -3.0))

    # --- overlays ----------------------------------------------------------------------------------
    w = S.windows
    all_passes = (w["lap"].first, w["lap"].last)
    overlay.title_page(cam, S, S.title_window, len(S.passes))
    overlay.fade_black(cam, "around.in", (1, 9), None, (1, 9))
    overlay.section_tag(cam, "around.cam", S.title, [all_passes])
    for j, p in enumerate(S.passes):
        overlay.lower_third(cam, f"around.{p.key}", p, j, len(S.passes), w[p.key])
    first = w["lap"].first
    track = []
    for f in range(all_passes[0], all_passes[1] + 1):
        x, y, _ = position((f - first) / FPS)
        track.append((f, x - CAMERA[0], y - CAMERA[1]))
    fov = 2 * math.degrees(math.atan(18.0 / LENS))
    overlay.map_inset(cam, "around", track, RADIUS, all_passes, fov, shade=all_passes)
    overlay.readout(cam, "around.itd", itd_shots(w["lap"]), cap=0.03, top=0.37)
    last = w["lap"].last
    overlay.fade_black(cam, "around.out", None, (last - 8, last), (last - 8, last))
    for o in bpy.data.objects:  # R4: nothing occludes
        if o.type == "MESH":
            o["sfx_occluder"] = False
    return base.finish(S, [(1, cam)], out)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(ap.parse_args(argv).out))
