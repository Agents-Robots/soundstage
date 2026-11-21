"""Build ``production`` (README.md) in Blender: the overlays only (title page, section tags, lower
thirds, callouts, fades), rendered with a transparent film and laid over the animations' frames by
``steps.py``. The .blend has no set and no sound: the sound comes from the animations' own renders.
Every text of a scene shows in its first ``TEXT_S`` seconds and fades out: the scenes build to their
ends.

    blender -b --factory-startup -y --python examples/showcase/sections/production/build.py -- [--out DIR]
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

from kit.blender import base, overlay  # noqa: E402
from kit.story import Window  # noqa: E402
from section import CALLOUTS, SECTION, TEXT_FADE, TEXT_S  # noqa: E402

S = SECTION


def build(out: Path) -> Path:
    scene = base.new_scene(S)
    scene.render.film_transparent = True
    scene.render.image_settings.color_mode = "RGBA"
    cam = base.camera("production.cam", (0, 0, 10), lens=35.0, rotation=(0, 0, 0))
    overlay.title_page(cam, S, S.title_window, len(S.passes))
    overlay.fade_black(cam, "production.in", (1, 9), None, (1, 9))
    for j, p in enumerate(S.passes):
        w = S.window(p.key)
        end = round(w.at(TEXT_S))
        for layer in (overlay.section_tag(cam, f"production.{p.key}", S.title, [(w.first, end)]),
                      overlay.lower_third(cam, f"production.{p.key}", p, j, len(S.passes), Window(w.first, end))):
            layer.opacity([(w.first, 1.0), (end - TEXT_FADE, 1.0), (end, 0.0)])
        body, a, b = CALLOUTS[p.key]
        overlay.callout(cam, f"production.{p.key}", body, (round(w.at(a)), round(w.at(b))))
    last = S.frame_end
    overlay.fade_black(cam, "production.out", None, (last - 8, last), (last - 8, last))
    return base.finish(S, [(1, cam)], out)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(ap.parse_args(argv).out))
