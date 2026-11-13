"""Build ``delay`` (README.md) in Blender: a lake at dusk, a carpenter on a jetty across it (300 mm
lens), fireworks from rafts and lightning over the hills (28 mm lens), both cameras at one place;
every event tagged once per pass, with ``sync_to_picture`` off and on.

    blender -b --factory-startup -y --python examples/showcase/sections/delay/build.py -- [--out DIR]
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
from section import CAMERA, CUT_S, EVENTS, PAD_SECONDS, SECTION, SYNC, place  # noqa: E402

from soundstage.blender import tag  # noqa: E402

S = SECTION
FPS = base.story.FPS
C = 343.0
HIT_DEG, RAISED_DEG = -50.0, -170.0
"""The carpenter's hammer arm (about X): striking the post, and raised."""
REACH = 0.743
"""Horizontal distance from the carpenter's origin to the hammer head at the strike (m)."""
DECK_Z = 0.55
SPARKS = 36


def land() -> None:
    v, f = base.box_geometry(1200, 90, 1.0, 0, -39, -0.5)
    base.mesh_object("delay.near_shore", v, f, base.surface("grass", 0.95))
    v, f = base.box_geometry(3000, 1400, 0.2, 0, 700, -0.4)
    base.mesh_object("delay.lake", v, f, base.surface("water", 0.06))
    v, f = base.box_geometry(585, 250, 1.4, -15 - 292.5, 176 + 125, -0.3)
    base.mesh_object("delay.far_shore", v, f, base.surface("grass", 0.95))
    v, f = base.box_geometry(3000, 900, 1.4, 0, 1350, -0.3)
    base.mesh_object("delay.hill_shore", v, f, base.surface("hill", 0.95))
    rnd = random.Random(3)
    for i in range(14):  # low hills beyond the lake
        x = -900 + i * 140 + rnd.uniform(-40, 40)
        hill = base.sphere(f"delay.hill{i}", 1.0, (x, rnd.uniform(1050, 1250), -40), base.surface("hill", 0.95),
                           segments=10, rings=6)
        hill.scale = (rnd.uniform(160, 260), rnd.uniform(120, 200), rnd.uniform(120, 190))
    for i in range(40):  # trees on the far shore behind the jetty
        t = models.tree(f"delay.tree{i}", rnd.uniform(8, 13), seed=i)
        t.location = (rnd.uniform(-300, -18), rnd.uniform(182, 300), 0.4)


def carpenter(hit: Vector, windows) -> object:
    """The jetty, a post, the carpenter in profile (facing +X) with a hammer; the arm keyed to strike
    the post on every hammer frame. Returns the figure."""
    x, y = hit.x, hit.y
    v, f = base.box_geometry(3.0, 14.0, 0.25, x - 0.4, y + 5.0, DECK_Z - 0.125)
    base.mesh_object("delay.jetty", v, f, base.surface("wood", 0.8))
    for i, (dx, dy) in enumerate(((-1.7, -1.8), (0.9, -1.8), (-1.7, 4), (0.9, 4))):
        base.cylinder(f"delay.jetty_leg{i}", 0.12, 2.0, (x - 0.4 + dx, y + dy, DECK_Z - 1.0), base.surface("wood", 0.8))
    base.cylinder("delay.post", 0.09, hit.z - 0.08 - DECK_Z, (x, y, (DECK_Z + hit.z - 0.08) / 2), base.surface("wood", 0.7))
    fig = models.figure("delay.carpenter", shirt="jacket")
    fig.location = (x - REACH, y, DECK_Z)
    fig.rotation_euler = (0, 0, math.pi / 2)  # facing +X: in profile to the camera
    arm = bpy.data.objects["delay.carpenter.arm_l"]  # the arm on the camera's side
    base.box("delay.hammer.handle", (0.04, 0.04, 0.38), (0, 0, -0.62 - 0.17), base.surface("wood", 0.7), arm)
    base.box("delay.hammer.head", (0.07, 0.2, 0.07), (0, 0, -0.62 - 0.33), base.surface("metal", 0.4), arm)
    lamp = bpy.data.objects.new("delay.worklight", bpy.data.lights.new("delay.worklight", "POINT"))
    base.link(lamp)
    lamp.location = (x - 0.4, y - 2.5, DECK_Z + 2.6)
    lamp.data.energy, lamp.data.color = 900.0, base.linear("#ffd9a0")
    lamp.visible_glossy = False  # no streak of its reflection on the water
    rad = math.radians
    for w in windows:
        hits = [w.at(s) for s in EVENTS["hammer"][5]]
        base.key(arm, "rotation_euler", w.first, (rad(RAISED_DEG), 0, 0), "CONSTANT")
        for h in hits:
            base.key(arm, "rotation_euler", h - 5, (rad(RAISED_DEG), 0, 0), "BEZIER")
            base.key(arm, "rotation_euler", h, (rad(HIT_DEG), 0, 0), "BEZIER")
            base.key(arm, "rotation_euler", h + 10, (rad(RAISED_DEG), 0, 0), "CONSTANT")
        base.key(arm, "rotation_euler", hits[-1] + 10, (rad(RAISED_DEG), 0, 0), "BEZIER")
        base.key(arm, "rotation_euler", hits[-1] + 26, (0, 0, 0), "CONSTANT")
    return fig


def hit_flashes(hit: Vector, windows) -> None:
    layer = overlay.Layer("delay.hit")
    for w in windows:
        for i, s in enumerate(EVENTS["hammer"][5]):
            f = w.at(s)
            ring = overlay.world_ring(f"delay.hit{w.first}_{i}", hit + Vector((0, -0.4, 0.1)), 0.3, 0.05,
                                      layer.mat("accent"), facing=CAMERA)
            base.key(ring, "scale", f, (1, 1, 1))
            base.key(ring, "scale", f + 10, (2.6, 2.6, 2.6))
            base.visible(ring, [(f, f + 10)])
    layer.opacity([(0, 1.0)])


def firework(name: str, centre: Vector, colour: str, frame: float) -> None:
    """A rocket rising from a raft for 1.2 s, then a burst of sparks 60 m across that fades out."""
    raft = Vector((centre.x, centre.y, -0.1))
    base.box(f"{name}.raft", (6, 6, 0.6), raft, base.surface("wood", 0.8))
    mat = base.glow(f"{name}.glow", colour, 0.0)
    sock = base.emission_socket(mat)
    base.key(sock, "default_value", frame - 0.01, 0.0, "CONSTANT")
    base.key(sock, "default_value", frame, 18.0, "LINEAR")
    base.key(sock, "default_value", frame + 45, 0.0, "CONSTANT")
    rocket = base.sphere(f"{name}.rocket", 0.9, raft, base.glow(f"{name}.rocket_glow", "spark_gold", 40.0), segments=8,
                         rings=4)
    base.key(rocket, "location", frame - 36, raft, "LINEAR")
    base.key(rocket, "location", frame, centre, "CONSTANT")
    base.visible(rocket, [(frame - 36, frame - 1)])
    rnd = random.Random(name)
    for i in range(SPARKS):
        z = 1 - 2 * (i + 0.5) / SPARKS  # spread on a sphere (Fibonacci)
        a = i * math.pi * (3 - math.sqrt(5))
        d = Vector((math.sqrt(1 - z * z) * math.cos(a), math.sqrt(1 - z * z) * math.sin(a), z))
        spark = base.sphere(f"{name}.spark{i}", 1.6, centre, mat, segments=6, rings=4)
        out = centre + d * 30 * rnd.uniform(0.85, 1.05)
        base.key(spark, "location", frame, centre, "BEZIER")
        base.key(spark, "location", frame + 15, out, "LINEAR")
        base.key(spark, "location", frame + 45, out + Vector((0, 0, -12)), "CONSTANT")
        base.visible(spark, [(frame, frame + 45)])
    base.no_occlusion(rocket)


def lightning(source: Vector, windows) -> None:
    """A bolt from the clouds through the thunder's source point to a hill, lit for 3 frames, and
    the sky and the sun brightened on those frames."""
    rnd = random.Random(11)
    top, ground = source + Vector((20, 15, 190)), source - Vector((20, 15, 190))
    pts = [top + (ground - top) * (k / 12) + Vector((rnd.uniform(-12, 12), 0, rnd.uniform(-5, 5))) for k in range(13)]
    pts[6] = source.copy()  # the thunder's source is the middle of the bolt
    verts, faces = [], []
    for k, p in enumerate(pts):
        verts += [p + Vector((-2.2, 0, 0)), p + Vector((2.2, 0, 0))]
        if k:
            faces.append((2 * k - 2, 2 * k - 1, 2 * k + 1, 2 * k))
    bolt = base.mesh_object("delay.bolt", verts, faces, base.glow("delay.bolt_glow", "bolt", 120.0))
    world_strength = bpy.context.scene.world.node_tree.nodes["Background"].inputs["Strength"]
    sun = bpy.data.objects["sun"].data
    base.key(world_strength, "default_value", 1, world_strength.default_value, "CONSTANT")
    base.key(sun, "energy", 1, sun.energy, "CONSTANT")
    normal_sky, normal_sun = world_strength.default_value, sun.energy
    flashes = []
    for w in windows:
        f = round(w.at(EVENTS["lightning"][5][0]))
        flashes.append((f, f + 2))
        base.key(world_strength, "default_value", f, 4.0, "CONSTANT")
        base.key(world_strength, "default_value", f + 3, normal_sky, "CONSTANT")
        base.key(sun, "energy", f, 6.0, "CONSTANT")
        base.key(sun, "energy", f + 3, normal_sun, "CONSTANT")
    base.visible(bolt, flashes)
    base.no_occlusion(bolt)


def build(out: Path) -> Path:
    base.new_scene(S)
    base.world("dusk")
    land()
    w = S.windows
    spots = {name: Vector(place(d, az, h)) for name, (d, az, h, *_rest) in EVENTS.items()}
    carpenter(spots["hammer"], w.values())
    hit_flashes(spots["hammer"], w.values())
    for i, colour in enumerate(("spark_gold", "spark_red", "spark_blue")):
        name = f"burst_{i + 1}"
        for k, wnd in w.items():
            firework(f"delay.{k}.{name}", spots[name], colour, wnd.at(EVENTS[name][5][0]))
    lightning(spots["lightning"], w.values())

    # --- sounds: one entry per event and pass; a click probe on each --------------------------------
    for name, (_d, _az, _h, sample, ref, times) in EVENTS.items():
        emitter = base.empty(f"delay.{name}", spots[name])
        for k, wnd in w.items():
            frames = [wnd.at(s) for s in times]
            common = {"mode": "once", "frame": frames if len(frames) > 1 else frames[0], "ref_distance": ref,
                      "sync_to_picture": SYNC[k]}
            tag.add_sound(emitter, sample, id=S.source_id(k, name), **common)
            tag.add_sound(emitter, "click.wav", id=S.probe_id(k, name), **common)

    # --- cameras and overlays ----------------------------------------------------------------------
    hit = spots["hammer"]
    tele = base.camera("delay.cam300", CAMERA, target=(hit.x - 0.4, hit.y, DECK_Z + 0.9 - 1.2), lens=300.0)
    wide = base.camera("delay.cam28", CAMERA, lens=28.0, rotation=base.aim(None, yaw_deg=-12.0, pitch_deg=7.0))
    shots = [(1, tele)]
    overlay.title_page(tele, S, S.title_window, len(S.passes))
    overlay.fade_black(tele, "delay.in", (1, 9), None, (1, 9))
    marks = [(343.0, "1 s"), (686.0, "2 s"), (1029.0, "3 s")]
    ticks = [d for d, *_ in EVENTS.values()]
    labels = [(171.5, "hammer"), (600.0, "fireworks"), (1029.0, "lightning")]
    for j, p in enumerate(S.passes):
        wnd = w[p.key]
        cut = round(wnd.at(CUT_S))
        shots += [(wnd.first, tele), (cut, wide)]
        for cam, span, events in ((tele, (wnd.first, cut - 1), ["hammer"]),
                                  (wide, (cut, wnd.last), ["burst_1", "burst_2", "burst_3", "lightning"])):
            name = f"delay.{p.key}.{cam.name.split('.')[-1]}"
            overlay.section_tag(cam, name, S.title, [span])
            overlay.lower_third(cam, name, p, j, len(S.passes), base.story.Window(*span))
            trips = []
            for e in events:
                d = EVENTS[e][0]
                for s in EVENTS[e][5]:
                    f = wnd.at(s)
                    trips.append((f, f if SYNC[p.key] else f + d / C * FPS, d))
            overlay.travel_ruler(cam, name, 1100.0, marks, ticks, labels, trips, span)
    last = w["synced"].last
    overlay.fade_black(wide, "delay.out", None, (last - 8, last), (last - 8, last))
    return base.finish(S, shots, out, settings={"pad_seconds": PAD_SECONDS})


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(p.parse_args(argv).out))
