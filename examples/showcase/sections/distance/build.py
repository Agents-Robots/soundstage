"""Build ``distance`` (README.md) in Blender: an open-air stage on a field by day, five cameras on a
line in front of it at 686 m down to 42.875 m, the music as one source on the stage front; per pass
the distance model and the air absorption on the source.

    blender -b --factory-startup -y --python examples/showcase/sections/distance/build.py -- [--out DIR]
"""

import argparse
import json
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

from kit.blender import base, models, overlay  # noqa: E402
from section import (  # noqa: E402
    BANDS_HZ,
    CAMERA_Z,
    DISTANCES,
    END_S,
    FADE_OUT_S,
    LEAD_FRAMES,
    LENS,
    PASS_SOURCE,
    REF_DISTANCE,
    SECTION,
    SHOT_FRAMES,
    SOURCE_Z,
    air_alpha_db_per_m,
    camera_y,
    level_db,
)

from soundstage.blender import tag  # noqa: E402

S = SECTION
FPS = base.story.FPS
LIGHT_FLASH = 40.0
"""Emission strength of the stage lights on a kick."""


def ground() -> None:
    v, f = base.box_geometry(1200, 2400, 0.2, 0, -700, -0.1)
    base.mesh_object("distance.field", v, f, base.surface("grass", 0.95))
    v, f = base.box_geometry(3.0, 760, 0.04, 0, -380, 0.02)
    base.mesh_object("distance.path", v, f, base.surface("paving", 0.95))


def scenery(rnd: random.Random) -> None:
    for i in range(70):  # two loose rows of trees along the path, for depth
        side = 1 if i % 2 else -1
        y = -720 + i * 11 + rnd.uniform(-4, 4)
        models.tree(f"distance.tree{i}", rnd.uniform(7, 11), seed=i).location = (side * rnd.uniform(28, 60), y, 0)
    for i in range(24):  # a wood behind the stage
        models.tree(f"distance.wood{i}", rnd.uniform(10, 15), seed=100 + i).location = (
            rnd.uniform(-70, 70), rnd.uniform(40, 90), 0)


def crowd(rnd: random.Random) -> None:
    shirts = ["shirt", "jacket", "car_red", "car_green", "truck_cab", "white", "car_grey"]
    for i in range(70):
        fig = models.figure(f"distance.fan{i}", shirt=shirts[i % len(shirts)])
        fig.location = (rnd.uniform(-11, 11), rnd.uniform(-22, -4), 0)
        fig.rotation_euler = (0, 0, math.pi + rnd.uniform(-0.3, 0.3))  # facing the stage (+Y)


def main_tags(music, w) -> None:
    """The music and its probes, one entry per pass (README.md, "Sounds" and "Known answers")."""
    for k, wnd in w.items():
        start = wnd.first - LEAD_FRAMES
        end = wnd.last + 1 - (END_S + FADE_OUT_S) * FPS  # the fade-out starts here
        common = {"frame": start, "end_frame": end, "ref_distance": REF_DISTANCE, **PASS_SOURCE[k]}
        tag.add_sound(music, "drum_loop.wav", id=S.source_id(k, "music"), loop_phase=0.0, loop_crossfade=0.0,
                      fade_out=FADE_OUT_S, group="music", **common)
        tag.add_sound(music, "noise_pink.wav", id=S.probe_id(k, "noise"), loop_phase=0.0, fade_out=FADE_OUT_S, **common)
        clicks = list(range(start, wnd.last + 1 - 15, 60))  # every 2 s; the last one arrives within the pass
        tag.add_sound(music, "click.wav", mode="once", frame=clicks, id=S.probe_id(k, "click"),
                      ref_distance=REF_DISTANCE, **PASS_SOURCE[k])


def lights_on_kicks(lights, w) -> None:
    """The stage lights flash on every kick, at emission time."""
    kicks = json.loads((base.SOUNDS / "make.json").read_text())["drum_loop"]["kicks_s"]
    sock = base.emission_socket(lights)
    base.key(sock, "default_value", 1, 0.0, "CONSTANT")
    for wnd in w.values():
        start, end = wnd.first - LEAD_FRAMES, wnd.last + 1 - (END_S + FADE_OUT_S) * FPS
        bar = 0
        while start + bar * 2 * FPS < end:
            for k in kicks:
                f = start + (bar * 2 + k) * FPS
                if f < end:
                    base.key(sock, "default_value", f - 0.01, 0.0)
                    base.key(sock, "default_value", f, LIGHT_FLASH)
                    base.key(sock, "default_value", f + 5, 0.0, "CONSTANT")
            bar += 1


def build(out: Path) -> Path:
    base.new_scene(S)
    base.world("day")
    rnd = random.Random(7)
    ground()
    scenery(rnd)
    crowd(rnd)
    _, lights = models.stage("distance.stage")
    music = base.empty("distance.music", (0, 0, SOURCE_Z))
    w = S.windows
    main_tags(music, w)
    lights_on_kicks(lights, w)

    cams = [base.camera(f"distance.cam{i + 1}", (0, camera_y(d), CAMERA_Z), target=(0, 4, 4.5), lens=LENS)
            for i, d in enumerate(DISTANCES)]
    shots = [(1, cams[0])]
    on: dict[int, dict[str, tuple[int, int]]] = {i: {} for i in range(len(cams))}
    for k, wnd in w.items():
        for i, cam in enumerate(cams):
            a = wnd.first + i * SHOT_FRAMES
            shots.append((a, cam))
            on[i][k] = (a, a + SHOT_FRAMES - 1)

    # --- overlays ----------------------------------------------------------------------------------
    overlay.title_page(cams[0], S, S.title_window, len(S.passes))
    overlay.fade_black(cams[0], "distance.in", (1, 9), None, (1, 9))
    bands = [f"{f // 1000}k" if f >= 1000 else str(f) for f in BANDS_HZ]
    for i, (cam, d) in enumerate(zip(cams, DISTANCES)):
        name = f"distance.cam{i + 1}"
        overlay.section_tag(cam, name, S.title, list(on[i].values()))
        overlay.readout(cam, name, [(f"{d:g} m", win) for win in on[i].values()])
        for j, p in enumerate(S.passes):
            overlay.lower_third(cam, f"{name}.{p.key}", p, j, len(S.passes), base.story.Window(*on[i][p.key]))
        for k in ("inverse", "air"):
            a, b = on[i][k]
            overlay.gauge(cam, f"{name}.{k}", [0, -6, -12, -18, -24], [(a, level_db(d))], (a, b))
        a, b = on[i]["air"]
        overlay.band_strip(cam, name, bands, [(a, [air_alpha_db_per_m(f) * d for f in BANDS_HZ])], (a, b))
    last = w["air"].last
    overlay.fade_black(cams[-1], "distance.out", None, (last - 8, last), (last - 8, last))
    return base.finish(S, shots, out)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(p.parse_args(argv).out))
