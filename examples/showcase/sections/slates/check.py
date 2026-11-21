"""Known answers of ``slates`` (README.md): silent; every card starts and ends on black.

    .venv/bin/python examples/showcase/sections/slates/check.py [--dir out/showcase/slates]
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from kit.checks import Check  # noqa: E402
from PIL import Image  # noqa: E402


def run(c: Check) -> None:
    x, _ = sf.read(c.dir / "slates.wav", always_2d=True)
    c.expect("WAV: digital silence", f"max {np.abs(x).max():.1e}", "0", not np.any(x))
    for key, (first, last) in c.windows.items():
        for f in (first, last):
            path = c.dir / "frames" / f"{f:05d}.png"
            level = float(np.asarray(Image.open(path).convert("L"), dtype=float).max()) if path.exists() else None
            c.expect(f"{key}: frame {f} black", "not rendered" if level is None else f"max {level:.0f} of 255", "0 to 2",
                     level is not None and level <= 2)


if __name__ == "__main__":
    Check.main(run, "slates")
