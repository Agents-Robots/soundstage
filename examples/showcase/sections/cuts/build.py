"""Build ``cuts`` (README.md) in Blender: an oval race track with a grandstand, three race cars, five
cameras (one on board the lead car) cut by markers into six shots per pass; a camera chip and a map
of the oval.

    blender -b --factory-startup -y --python examples/showcase/sections/cuts/build.py -- [--out DIR]
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
    CAM_A,
    CAM_C,
    CAM_D,
    CAM_E,
    CAMERAS,
    CARS,
    ENGINE_Z,
    LAP,
    ON_BOARD,
    RACE_PITCH,
    SECTION,
    SHOT_FRAMES,
    SHOTS,
    STRAIGHT,
    TURN_R,
    C,
    car_s,
    lead_distance,
    outward,
    track_point,
)

from soundstage.blender import tag  # noqa: E402

S = SECTION
FPS = base.story.FPS
PAINTS = ("race_blue", "car_red", "bike_green")
END_S = 13.6
"""The loops end here and fade out over the 0.5 s after: from camera A, up to 190 m away, the end
arrives 0.55 s later, 0.35 s before the pass ends (S3)."""
FADE_OUT_S = 0.5
TRACK_W = 12.0
"""The asphalt; the cars' line runs 2 m inside its middle."""


def oval(d: float, n: int = 240) -> list[tuple[float, float]]:
    """The line offset d metres outwards, as n points."""
    return [outward(LAP * i / n, d, 0.0)[:2] for i in range(n)]


def strip(name: str, inner: float, outer: float, material, z: float) -> None:
    a, b = oval(inner), oval(outer)
    n = len(a)
    verts = [(x, y, z) for x, y in a] + [(x, y, z) for x, y in b]
    faces = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    base.mesh_object(name, verts, faces, material)


def circuit(rnd: random.Random) -> None:
    base.box("cuts.ground", (1600, 1400, 0.2), (STRAIGHT / 2, TURN_R, -0.1), base.surface("grass", 0.95))
    strip("cuts.asphalt", -TRACK_W / 2 - 2, TRACK_W / 2 - 2, base.surface("asphalt", 0.9), 0.02)
    strip("cuts.kerb_in", -TRACK_W / 2 - 2.8, -TRACK_W / 2 - 2, base.surface("kerb_red", 0.8), 0.03)
    strip("cuts.kerb_out", TRACK_W / 2 - 2, TRACK_W / 2 - 1.2, base.surface("white", 0.8), 0.03)
    base.box("cuts.start_line", (0.6, TRACK_W, 0.01), (0, 2.0, 0.035), base.surface("white", 0.6))
    for i in range(0, 400):  # the armco along the outside: posts every 2.5 m, two rails
        s = LAP * i / 400
        x, y, h = track_point(s)
        if 300 < s < 340:  # open at camera C's place
            continue
        post = base.box(f"cuts.armco_post{i}", (0.1, 0.1, 0.75), outward(s, TRACK_W / 2 + 1.5, 0.375),
                        base.surface("metal"))
        post.rotation_euler = (0, 0, h)
    for k, z in enumerate((0.45, 0.7)):
        a, b = oval(TRACK_W / 2 + 1.45), oval(TRACK_W / 2 + 1.55)
        n = len(a)
        verts = [(x, y, z - 0.1) for x, y in a] + [(x, y, z - 0.1) for x, y in b]
        verts += [(x, y, z + 0.1) for x, y in a] + [(x, y, z + 0.1) for x, y in b]
        faces = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        faces += [(i, (i + 1) % n, 2 * n + (i + 1) % n, 2 * n + i) for i in range(n)]
        faces += [(n + i, n + (i + 1) % n, 3 * n + (i + 1) % n, 3 * n + i) for i in range(n)]
        base.mesh_object(f"cuts.armco{k}", verts, faces, base.surface("armco", 0.4))
    stand = models.grandstand("cuts.grandstand", 120.0, rows=30, seed=3)
    stand.location = (CAM_D[0], CAM_D[1] + 5.0, 0)
    for i in range(60):
        a = rnd.uniform(0, 2 * math.pi)
        r = rnd.uniform(140, 260)
        models.tree(f"cuts.tree{i}", rnd.uniform(8, 13), seed=100 + i).location = (
            STRAIGHT / 2 + r * 1.4 * math.cos(a), TURN_R + r * math.sin(a), 0)
    base.box("cuts.pit", (120, 14, 4), (STRAIGHT / 2, TURN_R, 2), base.surface("hangar", 0.8))  # infield building


def drive(cars) -> None:
    """Every car on every frame: location, heading along the line, wheels turning; each pass restarts
    the race (a teleport the engine detects)."""
    for k, car in enumerate(cars):
        wheels = [o for o in car.children if ".wheel" in o.name]
        for f in range(1, S.frame_end + 1):
            w = S.window("one_mic") if f < S.window("per_camera").first else S.window("per_camera")
            t = max(0, f - w.first) / FPS
            s = car_s(k, t)
            x, y, h = track_point(s)
            base.key(car, "location", f, (x, y, models.VEHICLE_Z))
            base.key(car, "rotation_euler", f, (0, 0, h + math.pi / 2))  # the model's front (-Y) along h
            for hub in wheels:
                base.key(hub, "rotation_euler", f, ((s - car_s(k, 0)) / hub["radius"], 0, 0))


def cameras(lead) -> dict:
    cams = {"a": base.camera("cuts.cam_a", CAM_A, target=(CAM_A[0] - 6, 0.0, 1.0), lens=CAMERAS["a"][1]),
            "c": base.camera("cuts.cam_c", CAM_C, target=track_point(320)[:2] + (1.0,), lens=CAMERAS["c"][1]),
            "d": base.camera("cuts.cam_d", CAM_D, target=(STRAIGHT + 30, TURN_R + 20, 0.0), lens=CAMERAS["d"][1]),
            "e": base.camera("cuts.cam_e", CAM_E, target=(CAM_E[0] + 40, 2 * TURN_R, 1.0), lens=CAMERAS["e"][1])}
    b = base.camera("cuts.cam_b", (0, 0, 0), lens=CAMERAS["b"][1], rotation=base.aim(None, 180.0, -4.0))
    b.parent = lead
    b.location = (ON_BOARD[0], ON_BOARD[1], ON_BOARD[2] - models.VEHICLE_Z)
    cams["b"] = b
    # C pans with the cars: on the lead car until 6.4 s, then over 0.4 s to the second
    for w in S.windows.values():
        for f in range(w.first + 2 * SHOT_FRAMES - 2, w.first + 3 * SHOT_FRAMES + 2):
            t = (f - w.first) / FPS
            m = min(max((t - 6.4) / 0.4, 0.0), 1.0)
            p0, p1 = (Vector(track_point(car_s(k, t))[:2] + (1.0,)) for k in (0, 1))
            aim = p0.lerp(p1, m * m * (3 - 2 * m))
            rot = (aim - Vector(CAM_C)).to_track_quat("-Z", "Y").to_euler()
            base.key(cams["c"], "rotation_euler", f, tuple(rot))
    return cams


def sounds(cars) -> None:
    engines = [base.empty(f"{car.name}.engine", (0, 1.0, ENGINE_Z - models.VEHICLE_Z), car) for car in cars]
    tyres = [base.empty(f"{car.name}.tyres", (0, 0, 0.3 - models.VEHICLE_Z), car) for car in cars]
    for k, w in S.windows.items():
        common = dict(frame=w.first, end_frame=w.at(END_S), fade_in=0.2, fade_out=FADE_OUT_S, loop_crossfade=0.0,
                      ref_distance=6.0)
        for i in range(CARS):
            tag.add_sound(engines[i], "race_engine.wav", id=S.source_id(k, f"engine_{i + 1}"), pitch=RACE_PITCH,
                          loop_phase="random", group="cars", **common)
            tag.add_sound(tyres[i], "tyre_noise.wav", id=S.source_id(k, f"tyres_{i + 1}"), gain_db=-8.0,
                          loop_phase="random", group="cars", **common)
        tag.add_sound(engines[0], "sine_1k.wav", id=S.probe_id(k, "sine"), loop_phase=0.0, group="probe", **common)
        tag.add_sound(engines[0], "click.wav", id=S.probe_id(k, "click"), mode="once", ref_distance=6.0, group="probe",
                      frame=[w.at(0.25 + 0.5 * i) for i in range(28)])
        tag.add_sound(cars[0], "crowd_bed.wav", id=S.source_id(k, "crowd"), spatial=False, gain_db=-24.0,
                      group="ambience", **{**common, "ref_distance": 1.0})


def shots() -> list[tuple[int, str]]:
    """(first frame, camera) of every shot of both passes."""
    return [(w.first + j * SHOT_FRAMES, name) for w in S.windows.values() for j, name in enumerate(SHOTS)]


def instruments(cams) -> None:
    """On each camera, for its shots: the camera chip, the map of the oval; on D the distance and
    delay of the lead car (``per_camera``)."""
    cuts = shots()
    windows = {name: [] for name in CAMERAS}
    for i, (f, name) in enumerate(cuts):
        last = cuts[i + 1][0] - 1 if i + 1 < len(cuts) else S.frame_end
        windows[name].append((f, last))
    all_passes = (S.window("one_mic").first, S.frame_end)
    track = [[] for _ in range(CARS)]
    for f in range(all_passes[0], all_passes[1] + 1):
        w = S.window("one_mic") if f < S.window("per_camera").first else S.window("per_camera")
        for k in range(CARS):
            x, y, _ = track_point(car_s(k, (f - w.first) / FPS))
            track[k].append((f, x, y))
    places = {"a": CAM_A, "c": CAM_C, "d": CAM_D, "e": CAM_E}
    one_mic = S.window("one_mic")
    for name, cam in cams.items():
        chip = [(f"{name.upper()} · {CAMERAS[name][0]}", win) for win in windows[name]]
        overlay.readout(cam, f"cuts.chip_{name}", chip, cap=0.028, top=0.05)
        marks = [(x, y, "muted", 0.008, [all_passes]) for x, y, _ in places.values()]
        if name in places:
            x, y, _ = places[name]
            marks.append((x, y, "accent", 0.011, windows[name]))
        marks.append((CAM_A[0], CAM_A[1], "accent", 0.016, [(one_mic.first, one_mic.last)]))  # the microphone
        movers = [(track[0], "accent", 0.009)] + [(track[k], "text", 0.007) for k in range(1, CARS)]
        if name == "b":
            movers[0] = (track[0], "accent", 0.012)
        overlay.plan_map(cam, f"cuts.map_{name}", all_passes, (-110.0, -100.0, 360.0, 290.0),
                         [(oval(0.0), "muted", 7.0)], marks, movers, top=0.115, width=0.2)
    w = S.window("per_camera")
    f0 = w.first + 3 * SHOT_FRAMES
    runs = []
    for f in range(f0, f0 + SHOT_FRAMES):
        d = lead_distance("d", (f - w.first) / FPS)
        body = f"{d:.0f} m · {d / C:.2f} s late"
        if runs and runs[-1][0] == body:
            runs[-1] = (body, (runs[-1][1][0], f))
        else:
            runs.append((body, (f, f)))
    overlay.readout(cams["d"], "cuts.delay", runs, cap=0.028, top=0.43)


def build(out: Path) -> Path:
    base.new_scene(S)
    base.world("day")
    circuit(random.Random(21))
    cars = [models.race_car(f"cuts.car{k + 1}", PAINTS[k]) for k in range(CARS)]
    drive(cars)
    sounds(cars)
    cams = cameras(cars[0])
    for o in bpy.data.objects:  # R4: the section shows cuts, not occlusion
        if o.type == "MESH":
            o["sfx_occluder"] = False

    # --- overlays ----------------------------------------------------------------------------------
    w = S.windows
    overlay.title_page(cams["a"], S, S.title_window, len(S.passes))
    overlay.fade_black(cams["a"], "cuts.in", (1, 9), None, (1, 9))
    for name, cam in cams.items():
        overlay.section_tag(cam, f"cuts.{name}", S.title, [(w["one_mic"].first, S.frame_end)])
        for j, p in enumerate(S.passes):
            overlay.lower_third(cam, f"cuts.{name}.{p.key}", p, j, len(S.passes), w[p.key])
    instruments(cams)
    last = w["per_camera"].last
    overlay.fade_black(cams[SHOTS[-1]], "cuts.out", None, (last - 8, last), (last - 8, last))
    markers = [(1, cams["a"])] + [(f, cams[name]) for f, name in shots() if f > 1]
    return base.finish(S, markers, out)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(ap.parse_args(argv).out))
