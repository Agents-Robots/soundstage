"""Build ``outro`` (README.md) in Blender: the end card on the kit's background colour, fading from
and to black. The code lines are checked first (R4): the two commands against the CLI's parser (in
the repo venv), the tag call against ``tag.add_sound``.

    blender -b --factory-startup -y --python examples/showcase/sections/outro/build.py -- [--out DIR]
"""

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import bpy  # noqa: E402
from kit.blender import base, overlay  # noqa: E402
from section import ALSO, SECTION, SEPARATOR, STATEMENT, STEPS, TAGLINE, credits  # noqa: E402

from soundstage.blender import tag  # noqa: E402

S = SECTION
LEFT, RIGHT = 0.10, 0.95


def check_code() -> None:
    """R4: the commands parse with the CLI's parser; the tag call validates."""
    py = base.REPO / ".venv" / "bin" / "python"
    for _, line in STEPS[1:]:
        args = shlex.split(line)
        assert args[0] == "soundstage", line
        subprocess.run([str(py), "-c", "import sys; from soundstage.cli import build_parser; "
                        "build_parser().parse_args(sys.argv[1:])", *args[1:]], check=True, cwd=base.REPO)
    car = bpy.data.objects.new("car", None)
    eval(STEPS[0][1], {"tag": tag, "car": car})  # raises if the call is invalid
    bpy.data.objects.remove(car)


def item_lines(items: tuple[str, ...], cap: float, width: float) -> list[str]:
    """A list joined by SEPARATOR on one line, or on two balanced lines broken between items."""
    whole = SEPARATOR.join(items)
    if overlay.text_width(whole, cap) <= width:
        return [whole]
    splits = [(SEPARATOR.join(items[:i]), SEPARATOR.join(items[i:])) for i in range(1, len(items))]
    fits = [s for s in splits if max(overlay.text_width(t, cap) for t in s) <= width]
    if not fits:
        raise overlay.TextTooWide(f"{whole!r} does not fit on two lines")
    return list(min(fits, key=lambda s: max(overlay.text_width(t, cap) for t in s)))


def build(out: Path) -> Path:
    check_code()
    base.new_scene(S)
    base.world("dusk")
    cam = base.camera("outro.cam", (0, 0, 10), lens=35.0, rotation=(0, 0, 0))
    hud = base.hud_of(cam)
    layer = overlay.Layer("outro.card")
    objs = [overlay.rect(hud, "outro.card.bg", -0.05, -0.05, 1.05, 1.05, layer.mat("bg"), z=0.0)]

    def text(name, body, cap, baseline, colour, x=LEFT, **kw):
        objs.append(overlay.text(hud, f"outro.{name}", body, cap, x, baseline, layer.mat(colour),
                                 max_width=RIGHT - x, **kw)[0])

    text("word", "soundstage", 0.085, 0.22, "text", bold=True)
    objs.append(overlay.rect(hud, "outro.rule", LEFT, 0.26 - 0.0028, LEFT + 0.06, 0.26 + 0.0028, layer.mat("accent"),
                             z=0.002))
    text("tagline", TAGLINE, 0.032, 0.32, "text")
    label_w = max(overlay.text_width(name, 0.028, bold=True) for name, _ in STEPS) + 0.03
    for i, (name, line) in enumerate(STEPS):
        y = 0.42 + 0.062 * i
        text(f"step{i}", name, 0.028, y, "accent", bold=True)
        text(f"code{i}", line, 0.024, y, "code", x=LEFT + label_w, kind="mono")
    for i, line in enumerate(overlay.wrap(STATEMENT, 0.028, RIGHT - LEFT)):
        text(f"statement{i}", line, 0.028, 0.66 + 0.05 * i, "text", bold=True)
    for i, line in enumerate(item_lines(ALSO, 0.022, RIGHT - LEFT)):
        text(f"also{i}", line, 0.022, 0.77 + 0.04 * i, "muted")
    y = 0.86
    if base.story.REPO_URL:
        text("where", base.story.REPO_URL, 0.024, y, "accent", kind="mono")
        y += 0.05
    body = credits((HERE.parents[1] / "sounds" / "sources.toml").read_text())
    for i, line in enumerate(overlay.wrap(body, 0.02, RIGHT - LEFT, lines=3)):
        text(f"credits{i}", line, 0.02, y + 0.036 * i, "muted")
    w = S.window("card")
    overlay.show(objs, [(w.first, w.last)])
    overlay.fade_black(cam, "outro.in", (1, 9), None, (1, 9))
    overlay.fade_black(cam, "outro.out", None, (w.last - 8, w.last), (w.last - 8, w.last))
    return base.finish(S, [(1, cam)], out)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(p.parse_args(argv).out))
