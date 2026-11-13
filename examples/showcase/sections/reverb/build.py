"""Build ``reverb`` (README.md) in Blender: one figure with a basketball in each of four sets (an
outdoor court, a living room, a gym, a church nave), the same action on the same frames; in the
church it then walks down the nave and claps again.

    blender -b --factory-startup -y --python examples/showcase/sections/reverb/build.py -- [--out DIR]
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
    AIM_Z,
    BALL_R,
    BOUNCES_S,
    CAMERA_Z,
    CLAPS_S,
    DECAY_S,
    DISTANCE,
    FLOOR,
    HANDS,
    LENS,
    REF_DISTANCE,
    ROOMS,
    SECTION,
    STEP_M,
    STEP_S,
    STEPS,
    TURN_S,
    WALK_CLAPS_S,
    WALK_END,
    WALK_START_S,
    direct_db,
    send_db,
    walk_y,
)

from soundstage.blender import tag  # noqa: E402

S = SECTION
FPS = base.story.FPS
ORIGIN = {"outdoors": Vector((0, 0, 0)), "livingroom": Vector((500, 0, 0)), "gym": Vector((1000, 0, 0)),
          "church": Vector((1500, 0, 0))}
"""Each set around its camera, which stands on its origin and looks along +Y."""
BALL_SAMPLES = ("basketball_1.wav", "basketball_2.wav", "basketball_3.wav")
CLAP_SAMPLES = ("handclap_1.wav", "handclap_2.wav")
HAND_Z = 1.0
"""The ball in the dribbling hand."""
TUCKED = (-0.33, 0.02, 1.12)
"""The ball under the left arm, relative to the figure."""


# --- sets ----------------------------------------------------------------------------------------------

def outdoor_court(o: Vector, rnd: random.Random) -> None:
    base.box("reverb.outdoors.ground", (600, 600, 0.2), o + Vector((0, 0, -0.1)), base.surface("grass", 0.95))
    base.box("reverb.outdoors.court", (16, 30, 0.04), o + Vector((0, 11, 0.02)), base.surface("court_asphalt", 0.9))
    lines = base.surface("gym_line", 0.6)
    for k, (sx, sy, x, y) in enumerate(((0.08, 28, -7.5, 11), (0.08, 28, 7.5, 11), (15, 0.08, 0, -3.0),
                                        (15, 0.08, 0, 25.0), (15, 0.08, 0, 11.0))):
        base.box(f"reverb.outdoors.line{k}", (sx, sy, 0.01), o + Vector((x, y, 0.045)), lines)
    hoop = models.basketball_hoop("reverb.outdoors.hoop")
    hoop.location = o + Vector((0, 15.0, 0))
    for k, (sx, sy, x, y) in enumerate(((0.05, 32, -9, 11), (0.05, 32, 9, 11), (18, 0.05, 0, 27))):
        base.box(f"reverb.outdoors.fence{k}", (sx, sy, 3.0), o + Vector((x, y, 1.5)), base.surface("fence", 0.8))
    for i in range(16):
        models.tree(f"reverb.outdoors.tree{i}", rnd.uniform(7, 11), seed=80 + i).location = o + Vector(
            (rnd.uniform(-40, 40), rnd.uniform(32, 55), 0))
    for i in range(4):
        h = models.house(f"reverb.outdoors.house{i}", 12, 10, rnd.choice((7, 9)), f"wall_{1 + i}", seed=90 + i)
        h.location = o + Vector((-45 + 30 * i, 70, 0))


def sets() -> None:
    outdoor_court(ORIGIN["outdoors"], random.Random(12))
    for key, make in (("livingroom", models.living_room), ("gym", models.gym), ("church", models.nave)):
        make(f"reverb.{key}.room").location = ORIGIN[key]


# --- the figure ----------------------------------------------------------------------------------------

def at(o: Vector, rel, y: float = DISTANCE) -> Vector:
    """A point given relative to a figure standing y metres ahead of the camera, facing it."""
    return o + Vector((rel[0], y + rel[1], rel[2]))


def clap(arm_l, arm_r, frame: float, rest: float | None = None) -> None:
    """Both arms forward, hands apart 5 frames before ``frame``, together on it, apart 5 after; back
    to ``rest`` degrees (hanging) after ``rest`` frames if given."""
    rad = math.radians
    for arm, side in ((arm_l, -1), (arm_r, 1)):
        apart = (rad(-68), 0, rad(-side * 8))
        together = (rad(-72), 0, rad(-side * 27))  # the hands meet in front of the chest (HANDS)
        base.key(arm, "rotation_euler", frame - 8, apart, "BEZIER")
        base.key(arm, "rotation_euler", frame - 4, apart, "BEZIER")
        base.key(arm, "rotation_euler", frame, together, "BEZIER")
        base.key(arm, "rotation_euler", frame + 4, apart, "BEZIER")
        if rest is not None:
            base.key(arm, "rotation_euler", frame + rest, (0, 0, 0), "CONSTANT")


def dribble(fig, ball, w, o: Vector) -> list[float]:
    """Three bounces, the ball caught and tucked under the left arm, two claps. Returns the contact
    frames of the ball."""
    arm_l = bpy.data.objects[f"{fig.name}.arm_l"]
    arm_r = bpy.data.objects[f"{fig.name}.arm_r"]
    hand = at(o, (FLOOR[0], FLOOR[1], HAND_Z))
    floor = at(o, (FLOOR[0], FLOOR[1], BALL_R))
    tucked = at(o, TUCKED)
    contacts = [w.at(s) for s in BOUNCES_S]
    base.key(ball, "location", w.first, hand, "BEZIER")
    for c in contacts:
        base.key(ball, "location", c - 0.3 * FPS, hand, "LINEAR")
        base.key(ball, "location", c, floor, "LINEAR")
    base.key(ball, "location", contacts[-1] + 0.3 * FPS, hand, "BEZIER")
    base.key(ball, "location", contacts[-1] + 0.55 * FPS, tucked, "CONSTANT")
    rad = math.radians
    base.key(arm_r, "rotation_euler", w.first, (rad(-38), 0, rad(-6)), "BEZIER")
    for c in contacts:
        base.key(arm_r, "rotation_euler", c - 0.3 * FPS, (rad(-42), 0, rad(-6)), "BEZIER")
        base.key(arm_r, "rotation_euler", c - 0.15 * FPS, (rad(-28), 0, rad(-6)), "BEZIER")
    base.key(arm_l, "rotation_euler", w.first, (0, 0, rad(-12)), "CONSTANT")
    for s in CLAPS_S:
        clap(arm_l, arm_r, w.at(s))
    end = w.at(CLAPS_S[-1]) + 12
    for arm in (arm_l, arm_r):
        base.key(arm, "rotation_euler", end, (0, 0, 0), "CONSTANT")
    return contacts


def figure(key: str):
    fig = models.figure(f"reverb.{key}.figure", shirt="shirt")
    fig.location = at(ORIGIN[key], (0, 0, 0))
    ball = base.sphere(f"reverb.{key}.ball", BALL_R, at(ORIGIN[key], (FLOOR[0], FLOOR[1], HAND_Z)),
                       base.surface("basketball", 0.6), segments=12, rings=8)
    ball["sfx_occluder"] = False
    return fig, ball


def walk(fig, w, o: Vector) -> list[tuple[float, str]]:
    """Clap, turn, walk down the nave, turn back, clap. Returns (contact frame, foot) of the steps."""
    arm_l = bpy.data.objects[f"{fig.name}.arm_l"]
    arm_r = bpy.data.objects[f"{fig.name}.arm_r"]
    clap(arm_l, arm_r, w.at(WALK_CLAPS_S[0]))  # the walk's arm swing takes over
    contacts = models.walk(fig, at(o, (0, 0, 0)), 0.0, w.first, STEPS, step_m=STEP_M, step_s=STEP_S,
                           first_s=WALK_START_S)
    turn = WALK_START_S - TURN_S
    base.key(fig, "rotation_euler", w.first, (0, 0, 0), "CONSTANT")
    base.key(fig, "rotation_euler", w.at(turn), (0, 0, 0), "BEZIER")
    base.key(fig, "rotation_euler", w.at(WALK_START_S), (0, 0, math.pi), "CONSTANT")
    end = WALK_START_S + STEPS * STEP_S
    base.key(fig, "rotation_euler", w.at(end + 0.05), (0, 0, math.pi), "BEZIER")
    base.key(fig, "rotation_euler", w.at(end + 0.05 + TURN_S), (0, 0, 2 * math.pi), "CONSTANT")
    clap(arm_l, arm_r, w.at(WALK_CLAPS_S[1]), rest=8)
    return contacts


# --- sounds --------------------------------------------------------------------------------------------

def sounds(walk_contacts) -> dict:
    """Ball and clap entries of the four room passes and the claps and steps of ``walk``; returns the
    emitters of ``walk`` for the overlays."""
    common = {"mode": "once", "ref_distance": REF_DISTANCE}
    for k in ROOMS:
        w, o = S.window(k), ORIGIN[k]
        floor = base.empty(f"reverb.{k}.floor_point", at(o, FLOOR))
        hands = base.empty(f"reverb.{k}.hands", at(o, HANDS))
        bounces = [w.at(s) for s in BOUNCES_S]
        for i, sample in enumerate(BALL_SAMPLES):
            tag.add_sound(floor, sample, id=S.source_id(k, f"ball_{i + 1}"), frame=bounces[i::len(BALL_SAMPLES)],
                          group="ball", **common)
        for i, (s, sample) in enumerate(zip(CLAPS_S, CLAP_SAMPLES)):
            tag.add_sound(hands, sample, id=S.source_id(k, f"clap_{i + 1}"), frame=[w.at(s)], group="claps", **common)
        tag.add_sound(floor, "click.wav", id=S.probe_id(k, "click_ball"), frame=bounces, group="probe", **common)
        tag.add_sound(hands, "click.wav", id=S.probe_id(k, "click_clap"), frame=[w.at(s) for s in CLAPS_S],
                      group="probe", **common)
    w, o = S.window("walk"), ORIGIN["church"]
    hands = base.empty("reverb.walk.hands", at(o, HANDS))
    claps = [w.at(s) for s in WALK_CLAPS_S]
    base.key(hands, "location", claps[0] + 0.3 * FPS, at(o, HANDS), "LINEAR")  # glides while silent
    base.key(hands, "location", claps[1] - 0.3 * FPS, at(o, HANDS, WALK_END), "CONSTANT")
    for i, (f, sample) in enumerate(zip(claps, CLAP_SAMPLES)):
        tag.add_sound(hands, sample, id=S.source_id("walk", f"clap_{i + 1}"), frame=[f], group="claps", **common)
    tag.add_sound(hands, "noise_burst.wav", id=S.probe_id("walk", "burst"), frame=claps, group="probe", **common)
    feet = []
    for j in range(4):  # steps 1, 5, 9 ... on footstep_1, steps 2, 6, 10 ... on footstep_2, ...
        foot = base.empty(f"reverb.walk.foot{j + 1}", at(o, (0, 0, 0.04)))
        mine = walk_contacts[j::4]
        for n, (f, side) in enumerate(mine):
            x = 0.11 if side == "l" else -0.11  # the figure faces +Y: its left foot is at +X
            p = o + Vector((x, walk_y((f - w.first) / FPS), 0.04))
            base.key(foot, "location", f, p, "CONSTANT" if n == len(mine) - 1 else "BEZIER")
            if n < len(mine) - 1:
                base.key(foot, "location", f + 0.5 * FPS, p, "LINEAR")  # held while it sounds
        tag.add_sound(foot, f"footstep_{j + 1}.wav", id=S.source_id("walk", f"step_{j + 1}"), frame=[f for f, _ in mine],
                      group="steps", **common)
        feet.append(foot)
    return {"hands": hands, "feet": feet}


# --- overlays ------------------------------------------------------------------------------------------

def rings() -> None:
    layer = overlay.Layer("reverb.ring")
    n = 0
    for k in ROOMS:
        w, o = S.window(k), ORIGIN[k]
        events = [(w.at(s), at(o, FLOOR) + Vector((0, 0, 0.02)), True) for s in BOUNCES_S]
        events += [(w.at(s), at(o, HANDS), False) for s in CLAPS_S]
        if k == "church":
            ww = S.window("walk")
            events += [(ww.at(s), at(o, HANDS, y), False) for s, y in zip(WALK_CLAPS_S, (DISTANCE, WALK_END))]
        for f, p, flat in events:
            ring = overlay.world_ring(f"reverb.ring{n}", p, 0.22 if flat else 0.2, 0.045, layer.mat("accent"),
                                      facing=None if flat else (o.x, o.y), flat=flat)
            base.key(ring, "scale", f, (1, 1, 1))
            base.key(ring, "scale", f + 8, (2.6, 2.6, 2.6))
            base.visible(ring, [(f, f + 8)])
            n += 1
    layer.opacity([(0, 1.0)])


def walk_instruments(cam) -> None:
    """Level bars of the direct sound and the reverberation it excites (relative to 3 m), and the
    distance, through ``walk``."""
    w = S.window("walk")
    direct, room, shots = [], [], []
    for f in range(w.first, w.last + 1):
        d = walk_y((f - w.first) / FPS)
        direct.append((f, direct_db(d)))
        room.append((f, send_db(d, DECAY_S["walk"]) - send_db(DISTANCE, DECAY_S["walk"])))
        body = f"{d:.1f} m"
        if shots and shots[-1][0] == body:
            shots[-1] = (body, (shots[-1][1][0], f))
        else:
            shots.append((body, (f, f)))
    overlay.level_bars(cam, "reverb.walk", [("direct", direct), ("room", room)], (w.first, w.last), top=0.06,
                       floor_db=-24.0)
    overlay.readout(cam, "reverb.walk.distance", shots, cap=0.03, top=0.22)


def build(out: Path) -> Path:
    base.new_scene(S)
    base.world("day")
    sets()
    figures = {k: figure(k) for k in ROOMS}
    for k in ROOMS:
        fig, ball = figures[k]
        dribble(fig, ball, S.window(k), ORIGIN[k])
    contacts = walk(figures["church"][0], S.window("walk"), ORIGIN["church"])
    base.visible(figures["church"][1], [(1, S.window("church").last)])  # the ball stays behind
    sounds(contacts)
    for o in bpy.data.objects:  # R4: the rooms contain camera and source; nothing occludes
        if o.type == "MESH":
            o["sfx_occluder"] = False
    cams = {}
    for k in ROOMS:
        o = ORIGIN[k]
        cams[k] = base.camera(f"reverb.cam_{k}", o + Vector((0, 0, CAMERA_Z)), target=o + Vector((0, DISTANCE, AIM_Z)),
                              lens=LENS)

    # --- overlays ----------------------------------------------------------------------------------
    w = S.windows
    first = cams["outdoors"]
    overlay.title_page(first, S, S.title_window, len(S.passes))
    overlay.fade_black(first, "reverb.in", (1, 9), None, (1, 9))
    for j, p in enumerate(S.passes):
        cam = cams["church" if p.key == "walk" else p.key]
        overlay.section_tag(cam, f"{cam.name}.{p.key}", S.title, [(w[p.key].first, w[p.key].last)])
        overlay.lower_third(cam, f"reverb.{p.key}", p, j, len(S.passes), w[p.key])
    rings()
    walk_instruments(cams["church"])
    last = w["walk"].last
    overlay.fade_black(cams["church"], "reverb.out", None, (last - 8, last), (last - 8, last))
    return base.finish(S, [(1, first)] + [(w[k].first, cams[k]) for k in ROOMS[1:]], out)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(ap.parse_args(argv).out))
