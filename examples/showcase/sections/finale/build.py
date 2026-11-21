"""Build ``finale`` (README.md) in Blender: the town at dusk turning to night with its side street,
the railway north of it and the hill beyond; the busker, the bell, the ambulance, the passer-by, the
train and its two level crossings, the scooter and the fireworks on one clock; seven cameras.

    blender -b --factory-startup -y --python examples/showcase/sections/finale/build.py -- [--out DIR]
"""

import argparse
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import bpy  # noqa: E402
from kit.blender import base, models, overlay, town  # noqa: E402
from mathutils import Vector  # noqa: E402
from section import (  # noqa: E402
    AMB_SOUND_S,
    BANG_GAIN_DB,
    BED_S,
    BELL_S,
    BURSTS,
    BUSK_S,
    BUSKER,
    BUSKER_YAW,
    CAB_EYE,
    CALLOUTS,
    CODE_S,
    CORNER_LENS,
    CROSS_CAM,
    CROSS_LENS,
    CROSS_YAW,
    DRONE,
    DRONE_AIM,
    DRONE_LENS,
    FADE_OUT_FRAMES,
    FIRE_CAM,
    FIRE_LENS,
    FIRE_PITCH,
    FIRE_YAW,
    HORN_S,
    ONBOARD_LENS,
    PASS_S,
    PASSERBY_Y,
    RAIL_Y,
    RAIL_Z,
    RENDER_CLAIM_S,
    RISE_S,
    SCOOTER_SOUND_S,
    SECTION,
    SHOTS,
    SOURCES,
    SPARK_M,
    SPARKS,
    SPREAD_M,
    SQUARE_CAM,
    SQUARE_LENS,
    STATS_S,
    STEP_M,
    STEP_S,
    STEPS,
    STREET_CAM,
    STREET_LENS,
    STREET_PITCH,
    STREET_YAW,
    TRAIN_SOUND_S,
    WALK_FROM_S,
    XING_BELL_S,
    XINGS,
    ZOOM_S,
    amb_x,
    burst_at,
    corner_cam,
    frame,
    hill_z,
    passerby_x0,
    scooter_at,
    shot_window,
    square_lens,
    square_yaw,
    tag_calls,
    train_front_x,
)

from soundstage.blender import tag  # noqa: E402

S = SECTION
FPS = base.story.FPS
LOOP = dict(loop_phase=0.0, loop_crossfade=0.0)
"""The kit's loops are seamless (sounds/README.md)."""


def sid(name: str) -> str:
    return S.source_id("town", name)


def pid(name: str) -> str:
    return S.probe_id("town", name)


def probe(obj, sample: str, name: str, **kw) -> None:
    tag.add_sound(obj, sample, id=pid(name), group="probe", **kw)


# --- set -----------------------------------------------------------------------------------------------

def night() -> None:
    """Dusk turning to night: the sky and the sun dim over the first 55 s, and the glow of the sunset
    (the sky's band 30 to 37 degrees up, seen when a camera looks up) fades into the night blue."""
    world = bpy.context.scene.world.node_tree
    strength = world.nodes["Background"].inputs["Strength"]
    sun = bpy.data.objects["sun"].data
    for target, path, a, b in ((strength, "default_value", 0.6, 0.3), (sun, "energy", 0.35, 0.03)):
        base.key(target, path, frame(0.0), a, "LINEAR")
        base.key(target, path, frame(55.0), b, "CONSTANT")
    moon = bpy.data.objects.new("moon", bpy.data.lights.new("moon", "SUN"))  # rises as the sun sets
    bpy.context.scene.collection.objects.link(moon)
    moon.data.color, moon.data.angle = base.colour("#aebfff")[:3], math.radians(1.0)
    moon.rotation_euler = (math.radians(50), 0, math.radians(150))
    base.key(moon.data, "energy", frame(0.0), 0.0, "LINEAR")
    base.key(moon.data, "energy", frame(55.0), 0.18, "CONSTANT")
    ramp = next(n for n in world.nodes if n.type == "VALTORGB").color_ramp
    for el in ramp.elements:
        if 0.51 < el.position < 0.61:
            base.key(el, "color", frame(0.0), tuple(el.color), "LINEAR")
            base.key(el, "color", frame(55.0), base.colour("#2c3150"), "CONSTANT")


def hill() -> None:
    xs = range(-1500, 1501, 100)
    ys = range(350, 1151, 50)
    verts = [(x, y, hill_z(x, y)) for y in ys for x in xs]
    n = len(xs)
    faces = [(j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i) for j in range(len(ys) - 1)
             for i in range(n - 1)]
    obj = base.mesh_object("finale.hill", verts, faces, base.surface("hill", 0.95))
    obj["sfx_occluder"] = False


def railway(rnd: random.Random) -> list:
    """The track, two level crossings with their roads, fields and trees along the line."""
    t = models.track("finale.track", -1100.0, 1500.0)
    t.location = (0, RAIL_Y, 0)
    crossings = []
    for i, x in enumerate(XINGS):
        c = models.crossing(f"finale.xing{i}")
        c.location = (x, RAIL_Y, 0)
        crossings.append(c)
        road = base.box(f"finale.xing{i}.lane", (6.0, 300.0, 0.06), (x, RAIL_Y + 30.0, 0.02), base.surface("asphalt", 0.9))
        road["sfx_occluder"] = False
    for k, (cx, cy, sx, sy) in enumerate(((420, RAIL_Y + 90, 240, 120), (700, RAIL_Y - 70, 260, 110),
                                          (-250, RAIL_Y + 80, 400, 110), (900, RAIL_Y + 100, 300, 160))):
        f = base.box(f"finale.field{k}", (sx, sy, 0.04), (cx, cy, 0.01), base.surface("field", 0.95))
        f["sfx_occluder"] = False
    n = 0
    while n < 70:
        x, side = rnd.uniform(-400, 1300), rnd.choice((-1, 1))
        y = RAIL_Y + side * rnd.uniform(14, 70)
        if any(abs(x - xx) < 12 for xx in XINGS) or (y < RAIL_Y and x < 140) or (abs(x - 420) < 120 and side > 0 and y < RAIL_Y + 30):
            continue
        models.tree(f"finale.rail_tree{n}", rnd.uniform(7, 12), seed=200 + n).location = (x, y, 0)
        n += 1
    return crossings


# --- action and sound ----------------------------------------------------------------------------------

def bell(places) -> None:
    strikes = [frame(t) for t in BELL_S]
    models.ring_bell(places["bell_pivot"], strikes)
    e = base.empty("finale.bell.sound", (0, 0, -0.6), places["bell_pivot"])
    tag.add_sound(e, "church_bell.wav", mode="once", frame=strikes, id=sid("bell"), ref_distance=80.0, group="bells")
    probe(e, "click.wav", "bell", mode="once", frame=strikes, ref_distance=80.0)


def ambulance() -> None:
    amb = models.ambulance("finale.ambulance")
    end = 26.0
    models.drive(amb, [(frame(0.0), Vector((amb_x(0.0), town.LANE, models.VEHICLE_Z))),
                       (frame(end), Vector((amb_x(end), town.LANE, models.VEHICLE_Z)))], heading_deg=90)
    base.visible(amb, [(1, frame(end))])
    models.blink(amb, [(frame(AMB_SOUND_S[0]), frame(AMB_SOUND_S[1] + 1.0))])
    bar = next(o for o in amb.children if o.name == "finale.ambulance.lightbar")
    span = dict(frame=frame(AMB_SOUND_S[0]), end_frame=frame(AMB_SOUND_S[1]), fade_in=1.0, fade_out=1.0, **LOOP)
    tag.add_sound(bar, "siren_two_tone.wav", id=sid("siren"), ref_distance=8.0, group="vehicles", **span)
    tag.add_sound(amb, "car_engine.wav", id=sid("amb_engine"), pitch=0.9, ref_distance=4.0, offset=(0, -1.9, 0),
                  group="vehicles", **span)
    tag.add_sound(amb, "tyre_noise.wav", id=sid("amb_tyres"), ref_distance=4.0, gain_db=-6.0, offset=(0, 1.9, -0.4),
                  group="vehicles", **span)
    probe(bar, "sine_1k.wav", "amb_sine", ref_distance=8.0, **span)
    probe(bar, "noise_pink.wav", "amb_noise", ref_distance=8.0, **span)
    probe(bar, "noise_pink.wav", "amb_open", ref_distance=8.0, occlusion=False, **span)


def busker() -> object:
    lamp = models.street_lamp("finale.busker_lamp", on=True, facing_deg=42.0)
    lamp.location = (BUSKER[0] + 4.0, BUSKER[1] - 4.5, 0.12)  # its light falls on the busker
    root, acc = models.busker("finale.busker")
    root.location = (BUSKER[0], BUSKER[1], 0.12)
    root.rotation_euler = (0, 0, math.radians(BUSKER_YAW + 180))
    models.play_accordion(acc, (frame(BUSK_S[0]), frame(BUSK_S[1])))
    span = dict(frame=frame(BUSK_S[0]), end_frame=frame(BUSK_S[1]), fade_in=0.3, fade_out=0.6, **LOOP)
    tag.add_sound(acc, "accordion_loop.wav", id=sid("busker"), ref_distance=4.0, group="music", **span)
    probe(acc, "noise_pink.wav", "busker_noise", ref_distance=4.0, **span)
    probe(acc, "noise_pink.wav", "busker_open", ref_distance=4.0, occlusion=False, **span)
    return acc


def passerby() -> None:
    walker = models.figure("finale.passerby", shirt="shirt_red")
    steps = models.walk(walker, Vector((passerby_x0(), PASSERBY_Y, 0.12)), -90, frame(WALK_FROM_S), steps=STEPS,
                        step_m=STEP_M, step_s=STEP_S)
    for i in range(4):
        frames = [f for j, (f, _) in enumerate(steps) if j % 4 == i]
        tag.add_sound(walker, f"footstep_{i + 1}.wav", mode="once", frame=frames, id=sid(f"step_{i + 1}"),
                      ref_distance=2.0, gain_db=-4.0, group="people")


def train(crossings) -> tuple[object, object]:
    """The train along +X through both crossings, the bells and lamps, the cab and its camera."""
    root, em, shell = models.train("finale.train", coaches=2)
    root.rotation_euler = (0, 0, math.radians(90))  # its front (-Y) towards +X
    base.runs(root, "location", [[(frame(t), (train_front_x(t), RAIL_Y, RAIL_Z)) for t in (0.0, 75.0)]])
    a, b = frame(TRAIN_SOUND_S[0]), frame(TRAIN_SOUND_S[1])
    for k in range(3):
        tag.add_sound(em[f"roll{k}"], "train_roll.wav", id=sid(f"train_roll_{k + 1}"), frame=a, end_frame=b,
                      fade_in=2.0, fade_out=2.0, ref_distance=8.0, gain_db=-3.0, group="railway", **LOOP)
    tag.add_sound(em["front"], "train_horn.wav", mode="once", frame=frame(HORN_S), id=sid("train_horn"),
                  ref_distance=60.0, group="railway")
    probe(em["front"], "sine_1k.wav", "horn_sine", frame=a, end_frame=b, fade_in=2.0, fade_out=2.0, ref_distance=60.0,
          **LOOP)
    probe(em["roll0"], "sine_1k.wav", "cab_sine", frame=a, end_frame=b, fade_in=2.0, fade_out=2.0, ref_distance=8.0,
          **LOOP)
    for i, c in enumerate(crossings):
        bell_ = next(o for o in c.children if o.name == f"finale.xing{i}.bell")
        f0, f1 = (frame(t) for t in XING_BELL_S[i])
        span = dict(frame=f0, end_frame=f1, fade_in=0.05, fade_out=0.3, **LOOP)
        tag.add_sound(bell_, "crossing_bell.wav", id=sid(f"xing_bell_{i + 1}"), ref_distance=6.0, gain_db=-8.0,
                      group="railway", **span)
        if i == 1:
            probe(bell_, "sine_1k.wav", "xing2_sine", ref_distance=6.0, **span)
        models.blink(c, [(f0, f1)], period_s=1.0, on=30.0, off=0.0)
    onboard = shot_window("onboard")
    inside = (round(frame(onboard[0])), round(frame(onboard[1])) - 1)
    for o in shell:
        base.visible(o, [(1, inside[0] - 1), (inside[1] + 1, S.frame_end)])
    cab = models.train_cab("finale.train.cab_inside")
    cab.parent = root
    cab.location = CAB_EYE
    cab.rotation_euler = (0, 0, math.radians(-90))  # the cab's +X along the train's front (-Y)
    base.visible(cab, [inside])
    cam = base.camera("finale.cam_onboard", (0, 0, 0), lens=ONBOARD_LENS, rotation=base.aim(None, 180, -2.0))
    cam.parent = root
    cam.location = CAB_EYE
    return root, cam


def scooter() -> None:
    sc = models.scooter("finale.scooter")
    t0, t1 = SCOOTER_SOUND_S[0] - 0.5, SCOOTER_SOUND_S[1] + 0.5
    p0, p1 = Vector(scooter_at(t0)), Vector(scooter_at(t1))
    d = p1 - p0
    heading = math.degrees(math.atan2(-d.x, d.y))
    z = models.VEHICLE_Z + 0.12 - 0.6  # the model's origin height, its engine at SCOOTER_Z
    models.drive(sc, [(frame(t0), p0 + Vector((0, 0, z))), (frame(t1), p1 + Vector((0, 0, z)))], heading_deg=heading)
    base.visible(sc, [(frame(t0), frame(t1))])
    e = base.empty("finale.scooter.sound")
    base.runs(e, "location", [[(frame(t0), p0), (frame(t1), p1)]])
    span = dict(frame=frame(SCOOTER_SOUND_S[0]), end_frame=frame(SCOOTER_SOUND_S[1]), fade_in=0.5, fade_out=0.5, **LOOP)
    tag.add_sound(e, "car_engine.wav", id=sid("scooter"), pitch=1.6, ref_distance=5.0, group="vehicles", **span)
    tag.add_sound(e, "tyre_noise.wav", id=sid("scooter_tyres"), ref_distance=5.0, gain_db=-8.0, group="vehicles", **span)
    probe(e, "noise_pink.wav", "scooter_noise", ref_distance=5.0, **span)


def fireworks() -> None:
    for i, (t, _, _, _, colour) in enumerate(BURSTS):
        centre = Vector(burst_at(i))
        launch = Vector((centre.x, centre.y, hill_z(centre.x, centre.y)))
        f = frame(t)
        models.firework(f"finale.burst{i + 1}", centre, colour, f, launch, sparks=SPARKS, spread_m=SPREAD_M,
                        spark_m=SPARK_M)
        e = base.empty(f"finale.burst{i + 1}.sound", centre)
        tag.add_sound(e, f"firework_bang_{i % 3 + 1}.wav", mode="once", frame=f, id=sid(f"burst_{i + 1}"),
                      ref_distance=600.0, gain_db=BANG_GAIN_DB, group="fireworks")
        probe(e, "click.wav", f"burst_{i + 1}", mode="once", frame=f, ref_distance=600.0)
    assert RISE_S * FPS == 36  # models.firework's rocket rises over 36 frames


# --- cameras -------------------------------------------------------------------------------------------

def cameras(onboard) -> dict:
    cams = {}
    drone = base.camera("finale.cam_overview", DRONE[0], target=DRONE_AIM, lens=DRONE_LENS)
    a, b = shot_window("overview")
    for f, p in ((frame(a), DRONE[0]), (frame(b), DRONE[1])):
        drone.location = p
        base.look(drone, DRONE_AIM)
        base.key(drone, "location", f, p, "BEZIER")
        base.key(drone, "rotation_euler", f, tuple(drone.rotation_euler), "BEZIER")
    cams["overview"] = drone
    cams["street"] = base.camera("finale.cam_street", STREET_CAM, lens=STREET_LENS,
                                 rotation=base.aim(None, STREET_YAW, STREET_PITCH))
    corner = base.camera("finale.cam_corner", corner_cam(20.0), lens=CORNER_LENS, rotation=base.aim(None, 90.0, 0.0))
    base.runs(corner, "location", [[(frame(t), corner_cam(t)) for t in (20.0, 31.0)]])
    cams["corner"] = corner
    cams["crossing"] = base.camera("finale.cam_crossing", CROSS_CAM, lens=CROSS_LENS, rotation=base.aim(None, CROSS_YAW, 2.0))
    cams["onboard"] = onboard
    sq = base.camera("finale.cam_square", SQUARE_CAM, lens=SQUARE_LENS[0], rotation=base.aim(None, square_yaw(), 0.0))
    hud = base.hud_of(sq)
    for t in ZOOM_S:
        mm = square_lens(t)
        base.key(sq.data, "lens", frame(t), mm, "LINEAR")
        base.key(hud, "location", frame(t), (0.0, 0.0, -mm / 50), "LINEAR")
    cams["square"] = sq
    cams["fireworks"] = base.camera("finale.cam_fireworks", FIRE_CAM, lens=FIRE_LENS,
                                    rotation=base.aim(None, FIRE_YAW, FIRE_PITCH))
    return cams


def build(out: Path) -> Path:
    base.new_scene(S)
    base.world("dusk")
    night()
    parked = [(-60, -town.PARKING, "car_blue"), (-47, town.PARKING, "car_grey"), (52, -town.PARKING, "car_green"),
              (66, town.PARKING, "car_red"), (-95, -town.PARKING, "car_grey"), (118, town.PARKING, "car_blue")]
    places = town.build("dusk", parked, side_street=True, lit=0.7)
    hill()
    crossings = railway(random.Random(5))

    bell(places)
    ambulance()
    busker()
    passerby()
    _, onboard = train(crossings)
    scooter()
    fireworks()
    bed = base.empty("finale.bed")
    tag.add_sound(bed, "town_bed.wav", id=sid("bed"), spatial=False, gain_db=-16.0, frame=frame(BED_S[0]), fade_in=2.0,
                  end_frame=frame(BED_S[1]), fade_out=1.5, group="ambience")

    cams = cameras(onboard)
    title = S.title_window
    overlay.title_page(cams["overview"], S, title, len(S.passes))
    overlay.fade_black(cams["overview"], "finale.in", (1, 9), None, (1, 9))
    last = S.frame_end
    overlay.fade_black(cams["fireworks"], "finale.out", None, (last - FADE_OUT_FRAMES, last),
                       (last - FADE_OUT_FRAMES, last))
    for i, (shot, body, a, b) in enumerate(CALLOUTS):
        overlay.callout(cams[shot], f"finale.call{i}", body, (round(frame(a)), round(frame(b))))
    calls = tag_calls()
    a, b = round(frame(CODE_S[0])), round(frame(CODE_S[1]))
    code = overlay.code_panel(cams["overview"], "finale", [(f"# the sound of this evening: {len(calls)} calls", "accent")]
                              + [(c, "code") for c, _ in calls], (a, b))
    code.opacity([(a, 0.0), (a + 9, 1.0), (b - 9, 1.0), (b, 0.0)])
    overlay.stats_card(cams["fireworks"], "finale", [
        (f"{SOURCES}", "sources in one scene"),
        (f"{sum(n for _, n in calls)}", "lines of Python to tag them"),
        (f"{PASS_S:.0f} s", f"of sound, rendered in under {RENDER_CLAIM_S} s"),
    ], (round(frame(STATS_S[0])), round(frame(STATS_S[1]))))
    shots = [(1, cams["overview"])] + [(round(frame(t)), cams[name]) for name, t in SHOTS[1:]]
    return base.finish(S, shots, out)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(p.parse_args(argv).out))
