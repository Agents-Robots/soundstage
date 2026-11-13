"""Known answers of ``outro`` (README.md): the WAV is digital silence; the first and last frames are
black; the text stays inside the 5 % margin (measured on the rendered card).

    .venv/bin/python examples/showcase/sections/outro/check.py [--dir out/showcase/outro]
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from kit.checks import Check  # noqa: E402
from PIL import Image  # noqa: E402

MARGIN = 0.05


def run(c: Check) -> None:
    x, _ = sf.read(c.dir / "outro.wav", always_2d=True)
    c.expect("WAV: 240 frames of digital silence (R1)", f"{len(x)} samples, max {np.abs(x).max():.1e}",
             "384000 samples, all 0", len(x) == 384000 and not np.any(x))
    frames = c.dir / "frames"
    first, last = c.man["frames"]
    for f in (first, last):
        path = frames / f"{f:05d}.png"
        level = float(np.asarray(Image.open(path).convert("L"), dtype=float).max()) if path.exists() else None
        c.expect(f"frame {f} black", "not rendered" if level is None else f"max {level:.0f} of 255", "0 to 2",
                 level is not None and level <= 2)
    card = np.asarray(Image.open(frames / f"{(first + last) // 2:05d}.png").convert("RGB"), dtype=float)
    bg = np.median(card.reshape(-1, 3), axis=0)
    ink = np.argwhere(np.abs(card - bg).max(axis=2) > 24)
    h, w = card.shape[:2]
    (y0, x0), (y1, x1) = ink.min(axis=0), ink.max(axis=0)
    box = (x0 / w, y0 / h, (x1 + 1) / w, (y1 + 1) / h)
    c.expect("text inside the 5 % margin (mid frame)", f"x {box[0]:.3f} to {box[2]:.3f}, y {box[1]:.3f} to {box[3]:.3f}",
             "0.050 to 0.950", min(box[:2]) >= MARGIN and max(box[2:]) <= 1 - MARGIN)


if __name__ == "__main__":
    Check.main(run, "outro")
