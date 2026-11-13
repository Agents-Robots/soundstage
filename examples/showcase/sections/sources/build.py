"""Build ``sources`` (README.md) in Blender: the town square by day; a car, its horn, the church
bell, a bed, three vehicles from one sample, and the groups as stems. The code panel of each pass
is formatted from the arguments the build passes to ``tag.add_sound`` (R2).

    blender -b --factory-startup -y --python examples/showcase/sections/sources/build.py -- [--out DIR]
"""

import argparse
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

from kit.blender import base, models, overlay, town  # noqa: E402
from mathutils import Vector  # noqa: E402
from section import (  # noqa: E402
    BELL_FRAMES,
    CAMERA,
    CAR_MIDDLE_S,
    HORN_FRAME,
    IDLE_X,
    PAN_S,
    PITCH,
    PITCH_ALONE_S,
    PITCH_CAMERA,
    PITCH_DISTANCE,
    PITCH_TOGETHER_S,
    SECTION,
    SPEED,
    STEMS_BELL_S,
    STEMS_MIDDLE_S,
)

from soundstage.blender import tag  # noqa: E402

S = SECTION
FPS = base.story.FPS
SPEAKER_FADE_S = 0.3


def value(v) -> str:
    """A Python literal as it would be typed: 4.0 -> 4."""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else f"{v:g}"
    if isinstance(v, str):
        return f'"{v}"'
    if isinstance(v, (list, tuple)):
        inner = ", ".join(value(x) for x in v)
        return f"[{inner}]" if isinstance(v, list) else f"({inner})"
    return str(v)


CODE_CHARS = 54
"""Longest code line in the panel; a longer call is wrapped after a comma, as Python is written."""


def add(obj, var: str, sample: str, shown: dict, **plumbing) -> list[str]:
    """``tag.add_sound`` with the arguments shown on screen plus the ones that tie the entry to its
    pass (id, frame window, fades); returns the call as shown, wrapped to ``CODE_CHARS``."""
    tag.add_sound(obj, sample, **shown, **plumbing)
    parts = [f'tag.add_sound({var}, "{sample}"'] + [f"{k}={value(v)}" for k, v in shown.items()]
    indent = " " * len("tag.add_sound(")
    lines, cur = [], parts[0]
    for part in parts[1:]:
        if len(cur) + 2 + len(part) + 1 > CODE_CHARS:
            lines.append(cur + ",")
            cur = indent + part
        else:
            cur += ", " + part
    return lines + [cur + ")"]


def coloured(lines: list[str], colour: str) -> list[tuple[str, str]]:
    return [(line, colour) for line in lines]


def window_of(w, start_s: float = 0.0, end_s: float | None = None, fade_s: float = SPEAKER_FADE_S) -> dict:
    """frame / end_frame / fades of a loop that runs within a pass and is silent before its end."""
    end = w.last + 1 - (2 * fade_s if end_s is None else w.seconds - end_s) * FPS
    return {"frame": w.at(start_s), "end_frame": end, "fade_in": fade_s, "fade_out": fade_s}


def main_view(yaw: float = 180.0):
    return base.aim(None, yaw_deg=yaw, pitch_deg=6.0)


def build(out: Path) -> Path:
    base.new_scene(S)
    base.world("day")
    parked = [(-48, town.PARKING, "car_blue"), (-41, -town.PARKING, "car_green"), (38, -town.PARKING, "car_grey"),
              (52, town.PARKING, "car_red")]
    places = town.build("day", parked)
    w = S.windows
    cam = base.camera("sources.cam", (*CAMERA, base.EYE), lens=28.0, rotation=main_view())
    pcam = base.camera("sources.pitch_cam", (*PITCH_CAMERA, base.EYE), lens=24.0, rotation=main_view())

    # --- the car: drives in loop, layers and stems; stands and idles in events and bed -------------
    car = models.car("car", "car_red")
    lane = lambda x: Vector((x, town.LANE, models.VEHICLE_Z))  # noqa: E731  towards -X
    for k, middle in (("loop", CAR_MIDDLE_S), ("layers", CAR_MIDDLE_S), ("stems", STEMS_MIDDLE_S)):
        win = w[k]
        t1 = (win.last - win.first) / FPS  # runs end on the pass's last frame: the next one keys the frame after
        models.drive(car, [(win.first, lane(SPEED * middle)), (win.last, lane(SPEED * (middle - t1)))], 90)
    for k in ("events", "bed"):
        models.drive(car, [(w[k].first, lane(IDLE_X)), (w[k].last, lane(IDLE_X))], 90)
    base.visible(car, [(1, w["bed"].last), (w["stems"].first, w["stems"].last)])

    code: dict[str, list[tuple[str, str]]] = {}
    engine = {"ref_distance": 4.0, "group": "vehicles"}
    tyres = {"offset": (0.0, 1.3, -0.4), "group": "vehicles"}
    line = add(car, "car", "car_engine.wav", engine, id=S.source_id("loop", "car_engine"), **window_of(w["loop"]))
    code["loop"] = coloured(line, "accent")
    grey = add(car, "car", "car_engine.wav", engine, id=S.source_id("layers", "car_engine"), **window_of(w["layers"]))
    t = add(car, "car", "tyre_noise.wav", tyres, id=S.source_id("layers", "car_tyres"), gain_db=-6.0,
            **window_of(w["layers"]))
    h = add(car, "car", "car_horn.wav", {"mode": "once", "frame": HORN_FRAME}, id=S.source_id("layers", "car_horn"),
            ref_distance=6.0)
    tag.add_sound(car, "click.wav", mode="once", frame=HORN_FRAME, id=S.probe_id("layers", "horn"), ref_distance=6.0)
    code["layers"] = coloured(grey, "muted") + coloured(t, "accent") + coloured(h, "accent")

    idle = {"ref_distance": 4.0}
    for k in ("events", "bed"):
        line = add(car, "car", "car_idle.wav", idle, id=S.source_id(k, "car_idle"), **window_of(w[k]))
        code[k] = coloured(line, "muted")
    tag.add_sound(car, "noise_pink.wav", id=S.probe_id("bed", "car"), ref_distance=4.0, loop_phase=0.0,
                  **window_of(w["bed"]))

    # --- the bell: three strikes in events, one in stems -------------------------------------------
    bell = places["bell"]
    line = add(bell, "bell", "church_bell.wav", {"mode": "once", "frame": list(BELL_FRAMES)},
               id=S.source_id("events", "bell"), ref_distance=40.0, group="bells")
    code["events"] += coloured(line, "accent")
    tag.add_sound(bell, "click.wav", mode="once", frame=list(BELL_FRAMES), id=S.probe_id("events", "bell"),
                  ref_distance=40.0)
    stems_bell = round(w["stems"].at(STEMS_BELL_S))
    models.ring_bell(places["bell_pivot"], list(BELL_FRAMES))
    models.ring_bell(places["bell_pivot"], [stems_bell])
    flashes = overlay.Layer("sources.flash")
    base.bpy.context.view_layer.update()
    bell_at = bell.matrix_world.translation.copy()
    for i, f in enumerate([*BELL_FRAMES, stems_bell]):
        ring = overlay.world_ring(f"sources.flash{i}", bell_at + Vector((0, 3.6, 0.5)), 1.6, 0.18, flashes.mat("accent"),
                                  facing=CAMERA)
        base.key(ring, "scale", f, (1, 1, 1))
        base.key(ring, "scale", f + 12, (2.4, 2.4, 2.4))
        base.visible(ring, [(f, f + 12)])
    flashes.opacity([(0, 1.0)])

    # --- bed: the camera pans 90 degrees to the right ----------------------------------------------
    root = base.empty("sources.root")
    bed = {"spatial": False, "group": "ambience"}
    line = add(root, "root", "town_bed.wav", bed, id=S.source_id("bed", "bed"), gain_db=-18.0, loop_phase=0.0,
               **window_of(w["bed"], fade_s=0.5))
    code["bed"] += coloured(line, "accent")
    rot0, rot1 = main_view(180.0), main_view(90.0)
    base.key(cam, "rotation_euler", 1, rot0, "CONSTANT")
    base.key(cam, "rotation_euler", w["bed"].first, rot0, "CONSTANT")
    base.key(cam, "rotation_euler", w["bed"].at(PAN_S[0]), rot0, "BEZIER")
    base.key(cam, "rotation_euler", w["bed"].at(PAN_S[1]), rot1, "CONSTANT")
    base.key(cam, "rotation_euler", w["stems"].first, rot0, "CONSTANT")

    # --- pitch: scooter, car and truck from one sample ---------------------------------------------
    pw = w["pitch"]
    vehicles = {"scooter": models.scooter("pitch.scooter"), "car": models.car("pitch.car", "car_blue"),
                "truck": models.truck("pitch.truck")}
    label = overlay.Layer("sources.pitch")
    code["pitch"] = []
    for name, obj in vehicles.items():
        p, x = PITCH[name]
        obj.location = (x, PITCH_CAMERA[1] - PITCH_DISTANCE, models.VEHICLE_Z)
        obj.rotation_euler = (0, 0, math.pi)  # facing the camera (+Y)
        base.visible(obj, [(pw.first, pw.last)])
        shown = {"pitch": p}
        a0, a1 = PITCH_ALONE_S[name]
        line = add(obj, name, "car_engine.wav", shown, id=S.source_id("pitch", name), ref_distance=4.0, loop_phase=0.0,
                   group="vehicles", **window_of(pw, a0, a1, fade_s=0.1))
        tag.add_sound(obj, "car_engine.wav", **shown, id=S.source_id("pitch", f"{name}_together"), ref_distance=4.0,
                      loop_phase=0.0, group="vehicles", **window_of(pw, *PITCH_TOGETHER_S, fade_s=0.2))
        tag.add_sound(obj, "sine_1k.wav", **shown, id=S.probe_id("pitch", name), ref_distance=4.0, loop_phase=0.0,
                      **window_of(pw, a0, a1, fade_s=0.1))
        code["pitch"] += coloured(line, "accent")
        height = {"scooter": 2.2, "car": 2.1, "truck": 4.0}[name]
        at = Vector((x, PITCH_CAMERA[1] - PITCH_DISTANCE, height))
        running = [(pw.at(a0), pw.at(a1)), (pw.at(PITCH_TOGETHER_S[0]), pw.last)]
        quiet = overlay.world_text(f"pitch.{name}.label", f"pitch={value(p)}", at, 0.32, label.mat("text"),
                                   (math.pi / 2, 0, math.pi), plate=label.mat("panel", 0.8))
        lit = overlay.world_text(f"pitch.{name}.label_on", f"pitch={value(p)}", at + Vector((0, 0.02, 0)), 0.32,
                                 label.mat("accent"), (math.pi / 2, 0, math.pi), plate=label.mat("panel", 0.8))
        base.visible(quiet, [(pw.first, round(pw.at(a0)) - 1), (round(pw.at(a1)) + 1, round(pw.at(PITCH_TOGETHER_S[0])) - 1)])
        mark = overlay.world_ring(f"pitch.{name}.ring", Vector((x, PITCH_CAMERA[1] - PITCH_DISTANCE, 0.3)), 2.0 if name != "truck" else 3.2,
                                  0.08, label.mat("accent"), flat=True)
        base.visible(lit, [(round(a), round(b)) for a, b in running])
        base.visible(mark, [(round(a), round(b)) for a, b in running])

    # --- stems: the drive, one strike and the bed together ------------------------------------------
    sw = w["stems"]
    groups = []
    for obj, sample, shown, extra in (
            (car, "car_engine.wav", engine, {"id": S.source_id("stems", "car_engine"), **window_of(sw)}),
            (car, "tyre_noise.wav", tyres, {"id": S.source_id("stems", "car_tyres"), "gain_db": -6.0, **window_of(sw)}),
            (bell, "church_bell.wav", {"mode": "once", "frame": stems_bell, "group": "bells"},
             {"id": S.source_id("stems", "bell"), "ref_distance": 40.0}),
            (root, "town_bed.wav", bed, {"id": S.source_id("stems", "bed"), "gain_db": -18.0, "loop_phase": 0.0,
                                         **window_of(sw, fade_s=0.5)})):
        tag.add_sound(obj, sample, **shown, **extra)
        if shown["group"] not in groups:
            groups.append(shown["group"])
    code["stems"] = [("soundstage render bake/scene.json -o mix.wav --stems", "accent"),
                     ("# one WAV per group: " + ", ".join(value(g) for g in groups), "muted")]
    cam_pos = Vector((*CAMERA, base.EYE))
    bell_dist = (bell_at - cam_pos).length
    vehicles_curve, bells_curve = [], []
    for f in range(sw.first, sw.last + 1, 2):
        t = (f - sw.first) / FPS
        d = (lane(SPEED * (STEMS_MIDDLE_S - t)) - cam_pos).length
        vehicles_curve.append((f, 20 * math.log10(min(1.0, 4.0 / d))))
        heard = stems_bell + bell_dist / 343.0 * FPS
        bells_curve.append((f, -99.0 if f < heard else 20 * math.log10(40.0 / bell_dist) - 60 * (f - heard) / FPS / 5.0))
    overlay.level_bars(cam, "sources.stems", [("vehicles", vehicles_curve), ("bells", bells_curve),
                                              ("ambience", [(sw.first, -18.0)])], (sw.first, sw.last), top=0.55)

    # --- overlays ----------------------------------------------------------------------------------
    tw = S.title_window
    overlay.title_page(cam, S, tw, len(S.passes))
    overlay.fade_black(cam, "sources.in", (1, 9), None, (1, 9))
    for i, p in enumerate(S.passes):
        pw_ = w[p.key]
        c = pcam if p.key == "pitch" else cam
        overlay.section_tag(c, f"sources.{p.key}", S.title, [(pw_.first, pw_.last)])
        overlay.lower_third(c, f"sources.{p.key}", p, i, len(S.passes), pw_)
        overlay.code_panel(c, f"sources.{p.key}", code[p.key], (pw_.first, pw_.last))
    last = w["stems"].last
    overlay.fade_black(cam, "sources.out", None, (last - 8, last), (last - 8, last))
    for o in [*vehicles.values()]:
        base.no_occlusion(o)
    shots = [(1, cam), (w["pitch"].first, pcam), (w["stems"].first, cam)]
    return base.finish(S, shots, out)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(p.parse_args(argv).out))
