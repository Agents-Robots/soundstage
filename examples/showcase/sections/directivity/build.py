"""Build ``directivity`` (README.md) in Blender: a business jet on an apron with its engines running,
a camera circling it once per pass; a map with the cones as lobes and a level bar per sound.

    blender -b --factory-startup -y --python examples/showcase/sections/directivity/build.py -- [--out DIR]
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
    AIM,
    CONES,
    FADE_IN_S,
    FADE_OUT_S,
    LENS,
    MARGIN_S,
    RADIUS,
    SECTION,
    C,
    camera_position,
    cone_at,
    cone_db,
    emitter,
)

from soundstage.blender import tag  # noqa: E402

S = SECTION
FPS = base.story.FPS
SAMPLES = {"whine": "jet_whine.wav", "roar": "jet_roar.wav"}
GROUPS = {"whine": "intake", "roar": "exhaust"}
PROBES = {"whine": "intake", "roar": "exhaust"}
LOBE_M = 20.0
"""Radius of a lobe at 0 dB on the map (metres of the scene); -24 dB is the centre."""


def apron(rnd: random.Random) -> None:
    v, f = base.box_geometry(900, 900, 0.2, 0, 0, -0.1)
    base.mesh_object("directivity.grass", v, f, base.surface("grass", 0.95))
    v, f = base.box_geometry(220, 160, 0.04, 0, 10, 0.02)
    base.mesh_object("directivity.apron", v, f, base.surface("apron", 0.9))
    line = base.surface("apron_line", 0.6)
    base.box("directivity.taxi", (0.25, 160, 0.01), (0, 10, 0.045), line, None)
    base.box("directivity.stop", (6.0, 0.25, 0.01), (0, -16.5, 0.045), line, None)
    for k, x in enumerate((-60, 60)):
        base.box(f"directivity.stand{k}", (0.25, 60, 0.01), (x, 10, 0.045), line, None)
    base.box("directivity.hangar", (60, 30, 14), (-20, 75, 7), base.surface("hangar", 0.8), None)
    base.box("directivity.hangar_door", (40, 0.2, 11), (-20, 59.9, 5.5), base.surface("metal", 0.6), None)
    terminal = models.house("directivity.terminal", 40, 14, 8, "wall_4", seed=2, roof="roof_dark")
    terminal.location = (70, 70, 0)
    terminal.rotation_euler = (0, 0, math.radians(180))
    for i in range(6):
        x = -90 + 36 * i
        base.box(f"directivity.mast{i}", (0.3, 0.3, 16), (x, -70, 8), base.surface("metal"), None)
    for i in range(14):
        models.tree(f"directivity.tree{i}", rnd.uniform(8, 12), seed=40 + i).location = (
            rnd.uniform(-150, 150), rnd.uniform(-130, -95), 0)


def end_frame(window) -> float:
    """Faded out where the sound still arrives MARGIN_S before the pass ends (S3)."""
    far = RADIUS + 2.5
    return window.last + 1 - (FADE_OUT_S + far / C + MARGIN_S) * FPS


def sounds(jet) -> None:
    """R5: four entries of the jet object, at its intakes and nozzles, each with its cone in `cones`."""
    for k, w in S.windows.items():
        common = dict(frame=w.first, end_frame=end_frame(w), fade_in=FADE_IN_S, fade_out=FADE_OUT_S,
                      loop_crossfade=0.0, ref_distance=RADIUS)
        for sound, (inner, outer, outer_db, axis) in CONES.items():
            cone = dict(cone_inner_deg=inner, cone_outer_deg=outer, cone_outer_gain_db=outer_db) if k == "cones" else {}
            for side, tag_ in ((-1, "l"), (1, "r")):
                tag.add_sound(jet, SAMPLES[sound], id=S.source_id(k, f"{sound}_{tag_}"), offset=emitter(sound, side),
                              forward_axis=axis, loop_phase="random", group=GROUPS[sound], **cone, **common)
            tag.add_sound(jet, "noise_pink.wav", id=S.probe_id(k, PROBES[sound]), offset=emitter(sound, -1),
                          forward_axis=axis, loop_phase=0.0, **cone, **common)


def circle(cam) -> None:
    """The camera on its circle on every frame, aimed at the jet (R6: the same lap in both passes)."""
    prev = None
    for w in S.windows.values():
        for f in range(w.first - (90 if w.first == S.window("omni").first else 0), w.last + 1):
            loc = Vector(camera_position(max(0, f - w.first) / FPS))
            base.key(cam, "location", f, tuple(loc))
            rot = (Vector(AIM) - loc).to_track_quat("-Z", "Y").to_euler()
            if prev is not None:
                rot.make_compatible(prev)
            prev = rot
            base.key(cam, "rotation_euler", f, Euler(rot), "LINEAR")


def map_shapes() -> list[list[tuple[float, float]]]:
    """The jet seen from above, nose up (map x = -X, map y = -Y)."""
    def flip(poly):
        return [(-x, -y) for x, y in poly]
    shapes = [[(-1.0, -12.0), (1.0, -12.0), (1.0, 4.2), (-1.0, 4.2)],  # fuselage
              [(-0.35, -14.6), (0.35, -14.6), (1.0, -12.0), (-1.0, -12.0)],  # nose
              [(-3.1, 3.3), (3.1, 3.3), (3.1, 4.7), (-3.1, 4.7)]]  # tailplane
    for side in (-1, 1):
        shapes.append([(side * 1.0, -8.2), (side * 7.0, -5.2), (side * 7.0, -4.1), (side * 1.0, -5.0)])
        shapes.append([(side * 1.28, -1.5), (side * 2.52, -1.5), (side * 2.52, 1.6), (side * 1.28, 1.6)])
    return [flip(p) for p in shapes]


def lobe(sound: str | None) -> list[tuple[float, float]]:
    """A cone's gain around the jet as a polar curve (0 dB at LOBE_M, -24 dB at the centre), nose up;
    ``None``: no cone (a circle)."""
    pts = []
    for a in range(0, 360, 4):
        beta = a if sound != "roar" else (180 - a) % 360  # whine: from the nose; roar: from the tail
        beta = min(beta, 360 - beta)
        db = 0.0 if sound is None else cone_db(beta, *CONES[sound][:3])
        r = LOBE_M * max(0.0, 1 + db / 24)
        pts.append((r * math.sin(math.radians(a)), r * math.cos(math.radians(a))))
    return pts


def build(out: Path) -> Path:
    base.new_scene(S)
    base.world("day")
    apron(random.Random(11))
    jet = models.jet("directivity.jet")
    for fan in (o for o in jet.children if ".fan_" in o.name):
        models.spin(fan, (1, S.frame_end), 1.3)
    sounds(jet)
    for o in bpy.data.objects:  # R4: the jet does not occlude, nor does anything else
        if o.type == "MESH":
            o["sfx_occluder"] = False
    cam = base.camera("directivity.cam", camera_position(0.0), target=AIM, lens=LENS)
    circle(cam)

    # --- overlays ----------------------------------------------------------------------------------
    w = S.windows
    all_passes = (w["omni"].first, w["cones"].last)
    overlay.title_page(cam, S, S.title_window, len(S.passes))
    overlay.fade_black(cam, "directivity.in", (1, 9), None, (1, 9))
    overlay.section_tag(cam, "directivity.cam", S.title, [all_passes])
    for j, p in enumerate(S.passes):
        overlay.lower_third(cam, f"directivity.{p.key}", p, j, len(S.passes), w[p.key])
    track = []
    for win in w.values():
        for f in range(win.first, win.last + 1):
            x, y, _ = camera_position((f - win.first) / FPS)
            track.append((f, -x, -y))
    omni_w, cones_w = (w["omni"].first, w["omni"].last), (w["cones"].first, w["cones"].last)
    lobes = [(lobe(None), "accent", 0.30, omni_w),
             (lobe("whine"), "accent", 0.45, cones_w), (lobe("roar"), "text", 0.30, cones_w)]
    overlay.lobe_map(cam, "directivity", track, RADIUS, all_passes, map_shapes(), lobes)
    bars = []
    for sound, label in (("whine", "intake"), ("roar", "exhaust")):
        curve = [(w["omni"].first, 0.0), (w["omni"].last, 0.0)]  # no cones: full
        for f in range(w["cones"].first, w["cones"].last + 1):
            t = (f - w["cones"].first) / FPS
            g = sum(10 ** (cone_at(sound, side, t) / 10) for side in (-1, 1)) / 2
            curve.append((f, 10 * math.log10(g)))
        bars.append((label, curve))
    overlay.level_bars(cam, "directivity", bars, all_passes, top=0.38, floor_db=-24.0)
    last = w["cones"].last
    overlay.fade_black(cam, "directivity.out", None, (last - 8, last), (last - 8, last))
    return base.finish(S, [(1, cam)], out)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(ap.parse_args(argv).out))
