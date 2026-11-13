"""Known answers of ``screen`` (README.md), asserted on the white-noise bursts at the hits: the level
difference between the channels below the head shadow, per hit and pass, against the pan formula
for the focal length at the hit; onsets on the hit's frame; the same summed level in both passes.

    .venv/bin/python examples/showcase/sections/screen/check.py [--dir out/showcase/screen]
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import numpy as np  # noqa: E402
from kit import measure  # noqa: E402
from kit.checks import Check  # noqa: E402
from section import hit_times, hitter, lens, level_difference_db  # noqa: E402

BAND = (200.0, 400.0)
"""Where the level difference is measured: below the head shadow, which adds 0.1 to 0.3 dB here."""
BURST_S = 0.1


def run(c: Check) -> None:
    rate = c.rate
    times = hit_times()
    diffs, sums = {}, {}
    for k in ("camera", "screen"):
        probes = {side: c.probe(k, side).audio for side in ("left", "right")}
        diffs[k], sums[k] = [], []
        late = []
        for i, t in enumerate(times):
            side = hitter(i)
            x = probes[side]
            seg = x[c.t(k, t):c.t(k, t + BURST_S)]
            left, right = (measure.band_db(seg[:, ch], rate, *BAND) for ch in (0, 1))
            diffs[k].append(right - left if side == "right" else left - right)
            sums[k].append(10 * np.log10(10 ** (left / 10) + 10 ** (right / 10)))
            onset = measure.onsets(x[c.t(k, t - 0.3):c.t(k, t + 0.3)], rate)
            late.append(1000 * (onset[0] - 0.3) if onset else float("nan"))
        worst = min(diffs[k])
        c.expect(f"{k}: every hit louder on its player's side", f"min {worst:+.2f} dB", "> 0", worst > 0)
        w = max(late, key=abs)
        c.expect(f"{k}: onsets on the hit's frame ({len(late)} hits)", f"max {w:+.2f} ms", "0 ± 1 ms", abs(w) <= 1.0)

    # camera: one level difference throughout the zoom
    want = [level_difference_db(hitter(i), lens(t), "camera") for i, t in enumerate(times)]
    err = max(abs(a - b) for a, b in zip(diffs["camera"], want))
    c.expect("camera: level difference at every hit, against the formula", f"max error {err:.2f} dB",
             f"{want[0]:.1f} dB ± 0.5", err <= 0.5)
    span = max(diffs["camera"]) - min(diffs["camera"])
    c.expect("camera: change over the zoom", f"{span:.2f} dB", "below 0.5 dB", span < 0.5)

    # screen: the hits move out with the players
    for label, idx in (("24 mm, hits 1 and 2", (0, 1)), ("55 mm, hits 8 to 10", (7, 8, 9))):
        for i in idx:
            want = level_difference_db(hitter(i), lens(times[i]), "screen")
            c.near(f"screen: level difference at {label} (hit {i + 1})", diffs["screen"][i], want, 0.7, "dB", 2)
    change = np.mean([diffs["screen"][i] for i in (7, 8, 9)]) - np.mean([diffs["screen"][i] for i in (0, 1)])
    c.expect("screen: change over the zoom", f"{change:.2f} dB", "at least 4.5 dB", change >= 4.5)

    d = max(abs(a - b) for a, b in zip(sums["camera"], sums["screen"]))
    c.expect("summed level of both channels, camera against screen, every hit", f"max {d:.2f} dB", "within 0.2 dB",
             d <= 0.2)


if __name__ == "__main__":
    Check.main(run, "screen")
