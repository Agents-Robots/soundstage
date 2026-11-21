"""Known answers of ``outro`` (README.md): each firework's bang arrives its travel time after the flash;
the first and last frames are black; the text stays inside the 5 % margin (measured on the rendered
card).

    .venv/bin/python examples/showcase/sections/outro/check.py [--dir out/showcase/outro]
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import numpy as np  # noqa: E402
from kit import measure, story  # noqa: E402
from kit.checks import Check  # noqa: E402
from PIL import Image  # noqa: E402
from section import BURSTS  # noqa: E402

MARGIN = 0.05
PANEL = 0.74


def run(c: Check) -> None:
    rate = c.rate
    stem = measure.mono(c.stem("card", "fireworks"))
    first = c.windows["card"][0]
    for i, (t, d, *_) in enumerate(BURSTS):
        sid = f"outro.card.burst_{i + 1}"
        flash = first + t * story.FPS
        want = (c.geo.arrival(sid, flash) - first) / story.FPS
        a = int(t * rate)
        seg = stem[a:a + int(2.5 * rate)]
        got = t + measure.onsets(seg, rate, threshold_db=measure.db(np.abs(seg).max()) - 30)[0]
        c.near(f"burst {i + 1} ({d:.0f} m): bang heard after the flash", got - t, want - t, 0.01, "s", 3)

    frames = c.dir / "frames"
    first_f, last_f = c.man["frames"]
    for f in (first_f, last_f):
        path = frames / f"{f:05d}.png"
        level = float(np.asarray(Image.open(path).convert("L"), dtype=float).max()) if path.exists() else None
        c.expect(f"frame {f} black", "not rendered" if level is None else f"max {level:.0f} of 255", "0 to 2",
                 level is not None and level <= 2)
    card = np.asarray(Image.open(frames / f"{(first_f + last_f) // 2:05d}.png").convert("RGB"), dtype=float)
    h, w = card.shape[:2]
    panel = card[:, :int(PANEL * w) - 4]
    bg = np.median(panel.reshape(-1, 3), axis=0)
    ink = np.argwhere(np.abs(panel - bg).max(axis=2) > 24)
    (y0, x0), (y1, x1) = ink.min(axis=0), ink.max(axis=0)
    box = (x0 / w, y0 / h, (x1 + 1) / w, (y1 + 1) / h)
    c.expect("text inside the 5 % margin (mid frame, on the panel)",
             f"x {box[0]:.3f} to {box[2]:.3f}, y {box[1]:.3f} to {box[3]:.3f}", "0.050 to 0.950",
             min(box[:2]) >= MARGIN and max(box[2:]) <= 1 - MARGIN)


if __name__ == "__main__":
    Check.main(run, "outro")
