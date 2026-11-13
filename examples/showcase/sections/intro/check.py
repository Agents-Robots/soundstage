"""Known answers of ``intro`` (README.md), asserted on the rendered section and its probe.

    .venv/bin/python examples/showcase/sections/intro/check.py [--dir out/showcase/intro]
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1])]

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from kit import measure, story  # noqa: E402
from kit.checks import Check  # noqa: E402

PROBE = "intro.probe.sound.siren"


def run(c: Check) -> None:
    x, _ = sf.read(c.dir / "intro.wav", always_2d=True)
    a, b = c.windows["silent"]
    c.expect("frames 1-195: digital silence (R2)", f"max {np.abs(x[:b * story.SAMPLES_PER_FRAME]).max():.1e}", "every sample 0",
             not np.any(x[:b * story.SAMPLES_PER_FRAME]))

    probe = c.probe("sound", "siren").audio
    rate = c.rate
    f_start = measure.frequency(probe[:int(0.25 * rate)], rate, 1000)
    c.near("probe, first 0.25 s of sound (README 1061.8 Hz)", f_start, 1000 * c.geo.rate(PROBE, c.frame("sound", 0.125)),
           0.003 * f_start, "Hz", 1)
    c.near("probe, first 0.25 s, against the README", f_start, 1061.8, 0.003 * 1061.8, "Hz", 1)
    f_late = measure.frequency(probe[int(8.875 * rate):int(9.125 * rate)], rate, 1000)
    c.near("probe 9 s after the start (README 945.0 Hz)", f_late, 1000 * c.geo.rate(PROBE, c.frame("sound", 9.0)),
           0.003 * f_late, "Hz", 1)
    c.near("probe 9 s after the start, against the README", f_late, 945.0, 0.003 * 945.0, "Hz", 1)

    times, freqs = measure.frequency_track(probe, rate, window_s=0.05, hop_s=0.005, near_hz=1000)
    ok = np.isfinite(freqs)
    i = np.flatnonzero(ok[:-1] & ok[1:] & (freqs[:-1] >= 1000) & (freqs[1:] < 1000))[0]
    crossing = times[i] + (freqs[i] - 1000) / (freqs[i] - freqs[i + 1]) * (times[i + 1] - times[i])
    # expected: the reception time whose playback rate is 1 (bisection on the geometry)
    lo, hi = c.frame("sound", 3.5), c.frame("sound", 5.5)
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if c.geo.rate(PROBE, mid) > 1 else (lo, mid)
    expected = (lo - c.windows["sound"][0]) / story.FPS
    c.near("probe passes 1000 Hz (README 4.47 s)", crossing, expected, 0.02, "s")
    st_t = np.arange(0, len(probe) - int(0.05 * rate), int(0.005 * rate))
    st = np.array([measure.rms_db(probe[s:s + int(0.05 * rate)]) for s in st_t])
    loudest = (st_t[np.argmax(st)] + 0.025 * rate) / rate
    # the cone points forwards: the siren is loudest shortly before it passes
    grid = np.arange(3.5, 5.5, 0.005)
    model = [c.geo.direct_gain_db(PROBE, c.frame("sound", t)) for t in grid]
    c.near("probe level highest where distance and cone predict", loudest, grid[int(np.argmax(model))], 0.1, "s")


if __name__ == "__main__":
    Check.main(run, "intro")
