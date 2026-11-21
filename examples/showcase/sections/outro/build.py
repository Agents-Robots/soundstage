"""Build ``outro`` (README.md) in Blender: the end card on a dark panel over a row of houses at night,
fireworks bursting to the right of it, fading from and to black. The code lines are checked first
(R4): the two commands against the CLI's parser (in the repo venv), the tag call against
``tag.add_sound``.

    blender -b --factory-startup -y --python examples/showcase/sections/outro/build.py -- [--out DIR]
"""

import argparse
import random
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import bpy  # noqa: E402
from kit.blender import base, models, overlay  # noqa: E402
from mathutils import Vector  # noqa: E402
from section import (  # noqa: E402
    ALSO,
    BED_DB,
    BED_S,
    BURSTS,
    INSTALL,
    RISE_S,
    SECTION,
    SEPARATOR,
    STATEMENT,
    STEPS,
    TAGLINE,
    WHERE,
    burst_at,
    credits,
)

from soundstage.blender import tag  # noqa: E402

S = SECTION
FPS = base.story.FPS
LEFT, RIGHT = 0.07, 0.70
PANEL = 0.74
"""The text column, and the right edge of the dark panel behind it; the fireworks burst to its right."""
PITCH, LENS = 10.0, 28.0
NIGHT = [(0.5, "#0b0d14"), (0.52, "#1d2236"), (0.6, "#121731"), (1.0, "#070a18")]


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


def night_sky() -> None:
    base.world("dusk")
    nt = bpy.context.scene.world.node_tree
    ramp = next(n for n in nt.nodes if n.type == "VALTORGB")
    els = ramp.color_ramp.elements
    while len(els) > len(NIGHT):
        els.remove(els[-1])
    while len(els) < len(NIGHT):
        els.new(0.9)
    for e, (pos, c) in zip(els, NIGHT):
        e.position, e.color = pos, base.colour(c)
    nt.nodes["Background"].inputs["Strength"].default_value = 0.5
    sun = bpy.data.objects["sun"]
    sun.data.energy, sun.data.color = 0.06, base.linear("#9fb3e0")


def town() -> None:
    """A row of houses 90 m ahead, right of the text panel, with some windows lit and trees between."""
    rnd = random.Random(5)
    base.box("outro.ground", (2000, 2000, 0.2), (0, 500, -0.1), base.surface("asphalt", 0.95))
    x = 18.0
    i = 0
    while x < 130.0:
        w = rnd.uniform(9.0, 14.0)
        h = models.house(f"outro.house{i}", w, 10.0, rnd.uniform(7.0, 13.0), f"wall_{rnd.randint(1, 5)}",
                         lit=0.45, seed=40 + i, roof="roof_dark")
        h.location = (x + w / 2, 90.0 + rnd.uniform(-2.0, 2.0), 0.0)
        if rnd.random() < 0.4:
            models.tree(f"outro.tree{i}", rnd.uniform(7, 10), seed=60 + i).location = (x + w + 1.0, 86.0, 0.0)
        x += w + rnd.uniform(1.0, 3.0)
        i += 1
    for k in range(4):
        models.street_lamp(f"outro.lamp{k}", on=True, facing_deg=180.0).location = (28.0 + 26.0 * k, 82.0, 0.0)


def fireworks() -> None:
    w = S.window("card")
    for i, (t, d, az, h, colour, sample) in enumerate(BURSTS):
        f = w.at(t)
        centre = Vector(burst_at(d, az, h))
        launch = Vector(burst_at(d, az, 0.0))
        models.firework(f"outro.burst{i + 1}", centre, colour, f, launch, sparks=60, spread_m=62.0, spark_m=3.2)
        e = base.empty(f"outro.burst{i + 1}.bang", tuple(centre))
        tag.add_sound(e, sample, mode="once", frame=f, id=f"outro.card.burst_{i + 1}", ref_distance=500.0,
                      group="fireworks")
    assert RISE_S * FPS == 36  # models.firework's rocket rises over 36 frames
    bed = base.empty("outro.bed")
    tag.add_sound(bed, "town_bed.wav", id="outro.card.bed", spatial=False, gain_db=BED_DB, frame=w.at(BED_S[0]),
                  fade_in=1.5, end_frame=w.at(BED_S[1]), fade_out=1.5, group="ambience")


def card(cam) -> None:
    hud = base.hud_of(cam)
    layer = overlay.Layer("outro.card")
    objs = [overlay.rect(hud, "outro.card.bg", -0.05, -0.05, PANEL, 1.05, layer.mat("bg", 0.88), z=0.0)]

    def text(name, body, cap, baseline, colour, x=LEFT, **kw):
        objs.append(overlay.text(hud, f"outro.{name}", body, cap, x, baseline, layer.mat(colour),
                                 max_width=RIGHT - x, **kw)[0])

    text("word", "SoundStage", 0.085, 0.15, "text", bold=True)
    objs.append(overlay.rect(hud, "outro.rule", LEFT, 0.19 - 0.0028, LEFT + 0.06, 0.19 + 0.0028, layer.mat("accent"),
                             z=0.002))
    text("tagline", TAGLINE, 0.032, 0.25, "text")
    label_w = max(overlay.text_width(name, 0.026, bold=True) for name, _ in STEPS) + 0.025
    for i, (name, line) in enumerate(STEPS):
        y = 0.33 + 0.055 * i
        text(f"step{i}", name, 0.026, y, "accent", bold=True)
        text(f"code{i}", line, 0.022, y, "code", x=LEFT + label_w, kind="mono")
    for i, line in enumerate(overlay.wrap(STATEMENT, 0.026, RIGHT - LEFT)):
        text(f"statement{i}", line, 0.026, 0.53 + 0.046 * i, "text", bold=True)
    text("get", "Get it", 0.03, 0.665, "accent", bold=True)
    get_w = overlay.text_width("Get it", 0.03, bold=True) + 0.02
    text("where", WHERE, 0.03, 0.665, "text", x=LEFT + get_w, bold=True)
    text("install", INSTALL, 0.02, 0.715, "code", kind="mono")
    for i, line in enumerate(item_lines(ALSO, 0.02, RIGHT - LEFT)):
        text(f"also{i}", line, 0.02, 0.775 + 0.036 * i, "muted")
    body = credits(*((HERE.parents[1] / "sounds" / f).read_text() for f in ("sources.toml", "animations.toml")))
    for i, line in enumerate(overlay.wrap(body, 0.02, RIGHT - LEFT, lines=3)):
        text(f"credits{i}", line, 0.02, 0.86 + 0.034 * i, "muted")
    w = S.window("card")
    overlay.show(objs, [(w.first, w.last)])


def build(out: Path) -> Path:
    check_code()
    base.new_scene(S)
    night_sky()
    town()
    fireworks()
    cam = base.camera("outro.cam", (0, 0, 1.6), rotation=base.aim(None, 0.0, PITCH), lens=LENS)
    card(cam)
    w = S.window("card")
    overlay.fade_black(cam, "outro.in", (1, 9), None, (1, 9))
    overlay.fade_black(cam, "outro.out", None, (w.last - 8, w.last), (w.last - 8, w.last))
    return base.finish(S, [(1, cam)], out)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(p.parse_args(argv).out))
