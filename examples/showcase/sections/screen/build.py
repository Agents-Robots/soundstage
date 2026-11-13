"""Build ``screen`` (README.md) in Blender: a tennis court seen from the side, a rally of ten hits per
pass, a zoom from 24 to 55 mm; a stereo bar under the picture and the focal length.

    blender -b --factory-startup -y --python examples/showcase/sections/screen/build.py -- [--out DIR]
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
    AIM,
    CAMERA,
    HIT_EVERY_S,
    LENS_WIDE,
    SECTION,
    ZOOM_S,
    heard_u,
    hit_point,
    hit_times,
    hitter,
    lens,
)

from soundstage.blender import tag  # noqa: E402

S = SECTION
FPS = base.story.FPS
SHIRTS = {"left": "shirt_red", "right": "shirt"}
SAMPLES = {"left": "tennis_hit_1.wav", "right": "tennis_hit_2.wav"}
REACH = 0.8
"""From the racket's swing axis to the middle of its head (models.tennis_player)."""
ARC_M = 9.81 * (HIT_EVERY_S / 2) ** 2 / 2
"""Height of the ball's arc above the hits: a free flight of HIT_EVERY_S."""


def setting(rnd: random.Random) -> None:
    v, f = base.box_geometry(800, 800, 0.2, 0, 60, -0.1)
    base.mesh_object("screen.ground", v, f, base.surface("grass", 0.95))
    models.tennis_court("screen.court")
    for i in range(16):  # trees behind the fence and at the ends
        x = rnd.uniform(-45, 45)
        y = rnd.uniform(16, 40) if abs(x) < 24 else rnd.uniform(-12, 40)
        models.tree(f"screen.tree{i}", rnd.uniform(8, 12), seed=i).location = (x, y, 0)
    club = models.house("screen.club", 16, 9, 6.5, "wall_1", seed=4)
    club.location = (-30, 26, 0)
    club.rotation_euler = (0, 0, math.radians(15))


def hit_frames(window) -> dict[str, list[int]]:
    out = {"left": [], "right": []}
    for i, t in enumerate(hit_times()):
        out[hitter(i)].append(round(window.at(t)))
    return out


def players() -> dict[str, object]:
    """The two players on their baselines, the racket meeting the ball at the hit point."""
    swings = {}
    for side, facing in (("left", 1), ("right", -1)):
        root, swing = models.tennis_player(f"screen.{side}", SHIRTS[side], facing)
        hp = Vector(hit_point(side))
        pivot = hp - Vector((facing * REACH, 0, 0))
        swing.location = (pivot.x, pivot.y, 0)
        root.location = (pivot.x - facing * 0.1, pivot.y + 0.32, 0)  # the body beside the racket arm
        frames = [f for w in S.windows.values() for f in hit_frames(w)[side]]
        models.swing_racket(swing, frames)
        swings[side] = swing
    return swings


def ball() -> None:
    """The ball on every frame of each pass: tossed up by the left player, then from racket to racket
    on an arc ARC_M high."""
    obj = base.sphere("screen.ball", 0.09, hit_point("left"), base.surface("ball", 0.5), segments=10, rings=6)
    times = hit_times()
    for w in S.windows.values():
        for f in range(w.first, w.last + 1):
            t = (f - w.first) / FPS
            if t <= times[0]:
                s = t / times[0]
                x, z = hit_point("left")[0], hit_point("left")[2] + 1.2 * 4 * s * (1 - s)
            else:
                i = min(int((t - times[0]) // HIT_EVERY_S), len(times) - 1)
                s = (t - times[i]) / HIT_EVERY_S
                a, b = hit_point(hitter(i))[0], hit_point("right" if hitter(i) == "left" else "left")[0]
                x, z = a + (b - a) * s, hit_point("left")[2] + ARC_M * 4 * s * (1 - s)
            base.key(obj, "location", f, (x, 0.0, z))


def sounds() -> dict[str, object]:
    emitters = {side: base.empty(f"screen.hit_{side}", hit_point(side)) for side in ("left", "right")}
    for k, w in S.windows.items():
        for side, frames in hit_frames(w).items():
            common = {"mode": "once", "frame": frames, "ref_distance": 40.0, "sync_to_picture": True}
            tag.add_sound(emitters[side], SAMPLES[side], id=S.source_id(k, f"hit_{side}"), group="hits", **common)
            tag.add_sound(emitters[side], "noise_burst.wav", id=S.probe_id(k, side), **common)
    return emitters


def rings() -> None:
    layer = overlay.Layer("screen.hit")
    for w in S.windows.values():
        for side, frames in hit_frames(w).items():
            for f in frames:
                ring = overlay.world_ring(f"screen.ring{f}", Vector(hit_point(side)), 0.35, 0.07, layer.mat("accent"),
                                          facing=CAMERA)
                base.key(ring, "scale", f, (1, 1, 1))
                base.key(ring, "scale", f + 8, (2.4, 2.4, 2.4))
                base.visible(ring, [(f, f + 8)])
    layer.opacity([(0, 1.0)])


def zoom(cam) -> None:
    """R1: only the focal length is keyed; the overlay root follows it, so that the overlays keep
    their size."""
    hud = base.hud_of(cam)

    def at(frame: float, mm: float, interpolation: str = "LINEAR") -> None:
        base.key(cam.data, "lens", frame, mm, interpolation)
        base.key(hud, "location", frame, (0.0, 0.0, -mm / 50), interpolation)

    at(1, LENS_WIDE)
    for w in S.windows.values():
        at(w.first, lens(0.0))
        at(w.at(ZOOM_S[0]), lens(ZOOM_S[0]))
        at(w.at(ZOOM_S[1]), lens(ZOOM_S[1]))
        at(w.last, lens(ZOOM_S[1]), "CONSTANT")  # the next pass starts wide again


def lens_shots() -> list[tuple[str, tuple[int, int]]]:
    runs: list[tuple[str, list[int]]] = []
    for w in S.windows.values():
        for f in range(w.first, w.last + 1):
            body = f"{lens((f - w.first) / FPS):.0f} mm"
            if runs and runs[-1][0] == body and runs[-1][1][1] == f - 1:
                runs[-1][1][1] = f
            else:
                runs.append((body, [f, f]))
    return [(body, (a, b)) for body, (a, b) in runs]


def build(out: Path) -> Path:
    base.new_scene(S)
    base.world("day")
    setting(random.Random(7))
    players()
    ball()
    sounds()
    rings()
    cam = base.camera("screen.cam", CAMERA, target=AIM, lens=LENS_WIDE)
    zoom(cam)

    # --- overlays ----------------------------------------------------------------------------------
    w = S.windows
    all_passes = (w["camera"].first, w["screen"].last)
    overlay.title_page(cam, S, S.title_window, len(S.passes))
    overlay.fade_black(cam, "screen.in", (1, 9), None, (1, 9))
    overlay.section_tag(cam, "screen.cam", S.title, [all_passes])
    for j, p in enumerate(S.passes):
        overlay.lower_third(cam, f"screen.{p.key}", p, j, len(S.passes), w[p.key])
        marks = []
        for i, t in enumerate(hit_times()):
            side = hitter(i)
            marks.append((round(w[p.key].at(t)), heard_u(side, lens(t), p.settings.get("pan_reference", "screen"))))
        overlay.stereo_bar(cam, f"screen.{p.key}", marks, (w[p.key].first, w[p.key].last))
    overlay.readout(cam, "screen.lens", lens_shots(), cap=0.035)
    last = w["screen"].last
    overlay.fade_black(cam, "screen.out", None, (last - 8, last), (last - 8, last))
    for o in bpy.data.objects:  # R6: nothing occludes
        if o.type == "MESH":
            o["sfx_occluder"] = False
    return base.finish(S, [(1, cam)], out)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(ap.parse_args(argv).out))
