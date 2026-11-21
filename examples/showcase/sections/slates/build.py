"""Build ``slates`` (README.md) in Blender: centred text cards on black, one per pass, each fading in
and out within its pass.

    blender -b --factory-startup -y --python examples/showcase/sections/slates/build.py -- [--out DIR]
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

from kit.blender import base, overlay  # noqa: E402
from section import CARDS, FADE, LINE_GAP, SECTION  # noqa: E402

S = SECTION


def build(out: Path) -> Path:
    base.new_scene(S)
    cam = base.camera("slates.cam", (0, 0, 10), lens=35.0, rotation=(0, 0, 0))
    hud = base.hud_of(cam)
    black = overlay.Layer("slates.black")
    overlay.show([overlay.rect(hud, "slates.black", -0.1, -0.1, 1.1, 1.1, black.mat("black"), z=0.0)],
                 [(1, S.frame_end)])
    for p in S.passes:
        w = S.window(p.key)
        layer = overlay.Layer(f"slates.{p.key}")
        lines, y = CARDS[p.key]
        objs = []
        for i, (body, cap, colour, bold) in enumerate(lines):
            if i:
                y += LINE_GAP * cap
            objs.append(overlay.text(hud, f"slates.{p.key}.{i}", body, cap, 0.5, y, layer.mat(colour), bold=bold,
                                     align="CENTER", max_width=0.9)[0])
            if p.key == "title" and i == 0:  # the accent rule under the wordmark, as on the title pages
                objs.append(overlay.rect(hud, "slates.title.rule", 0.47, y + 0.04 - 0.0028, 0.53, y + 0.04 + 0.0028,
                                         layer.mat("accent"), z=0.002))
                y += 0.045
        overlay.show(objs, [(w.first, w.last)])
        layer.opacity([(w.first, 0.0), (w.first + FADE, 1.0), (w.last - FADE, 1.0), (w.last, 0.0)])
    return base.finish(S, [(1, cam)], out)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(ap.parse_args(argv).out))
