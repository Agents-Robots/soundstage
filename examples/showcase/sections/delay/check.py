"""Known answers of ``delay`` (README.md), asserted on the click probes: arrival after each event's
frame (physical: distance / 343 m/s; synced: on the frame), equal level and spectrum in both
passes, the air's loss on the thunder, and the bake's padding.

    .venv/bin/python examples/showcase/sections/delay/check.py [--dir out/showcase/delay]
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import numpy as np  # noqa: E402
from kit import measure, story  # noqa: E402
from kit.checks import C, Check  # noqa: E402
from section import EVENTS  # noqa: E402

from soundstage.engine.filters import iso9613_alpha  # noqa: E402

THIRDS_HZ = (250, 1000, 4000, 8000)
"""Third-octave bands compared between the passes."""


def onset(x: np.ndarray, rate: int, near_s: float) -> float:
    """Time (s) of the strongest peak within 0.1 s of ``near_s`` (a click's arrival), with
    sub-sample refinement."""
    m = np.abs(measure.mono(x))
    a = int((near_s - 0.1) * rate)
    i = a + int(np.argmax(m[a:a + int(0.2 * rate)]))
    p, q, r = m[i - 1], m[i], m[i + 1]
    d = p - 2 * q + r
    return (i + (0.5 * (p - r) / d if d else 0.0)) / rate


def thirds_db(x: np.ndarray, rate: int) -> np.ndarray:
    f = np.fft.rfftfreq(len(x), 1 / rate)
    p = np.abs(np.fft.rfft(measure.mono(x))) ** 2
    return np.array([10 * np.log10(p[(f >= fc * 2 ** -(1 / 6)) & (f < fc * 2 ** (1 / 6))].sum()) for fc in THIRDS_HZ])


def run(c: Check) -> None:
    rate = c.rate
    first = {k: w[0] for k, w in c.windows.items()}
    spectra = {}
    for k in ("physical", "synced"):
        for name, (d, *_rest, times) in EVENTS.items():
            x = c.probe(k, name).audio
            for j, s in enumerate(times):
                frame = first[k] + s * story.FPS
                got = onset(x, rate, s + (d / C if k == "physical" else 0.0))
                if k == "physical":
                    want = (c.geo.arrival(c.key + f".probe.{k}.{name}", frame) - first[k]) / story.FPS
                    c.near(f"physical: {name} click {j + 1}, after its frame", 1000 * (got - s), 1000 * (want - s), 1.0,
                           "ms", 2)
                    c.near(f"physical: {name} distance / 343 m/s", 1000 * (want - s), 1000 * d / C, 0.05, "ms", 2)
                else:
                    c.near(f"synced: {name} click {j + 1}, after its frame", 1000 * (got - s), 0.0, 1.0, "ms", 2)
                i = int(got * rate)
                spectra[(k, name, j)] = thirds_db(x[i - int(0.01 * rate):i + int(0.04 * rate)], rate)
    for name, (*_rest, times) in EVENTS.items():
        for j in range(len(times)):
            diff = np.abs(spectra[("synced", name, j)] - spectra[("physical", name, j)]).max()
            c.expect(f"{name} click {j + 1}: synced = physical in level and spectrum", f"max {diff:.3f} dB",
                     "within 0.1 dB", diff <= 0.1)

    # the thunder's click with and without the air: the loss in the 4 kHz octave over 1029 m
    s = EVENTS["lightning"][5][0]
    wet = c.probe("physical", "lightning").audio
    dry = c.probe("physical", "lightning", extra={"air_absorption": 0.0}).audio
    i = int(onset(dry, rate, s + EVENTS["lightning"][0] / C) * rate)
    seg = slice(i - int(0.02 * rate), i + int(0.08 * rate))
    f = np.fft.rfftfreq(seg.stop - seg.start, 1 / rate)
    pw, pd = (np.abs(np.fft.rfft(measure.mono(y[seg]))) ** 2 for y in (wet, dry))
    band = (f >= 4000 / np.sqrt(2)) & (f < 4000 * np.sqrt(2))
    got = 10 * np.log10(pw[band].sum() / pd[band].sum())
    d = float(c.geo.distance(c.key + ".probe.physical.lightning", first["physical"] + s * story.FPS))
    want = 10 * np.log10(np.sum(pd[band] * 10 ** (-iso9613_alpha(f[band]) * d / 10)) / pd[band].sum())
    c.near(f"thunder: air loss, 4 kHz octave over {d:.0f} m (ISO 9613-1 {iso9613_alpha(4000.0) * d:.1f} dB at 4 kHz)",
           got, want, 2.0, "dB", 1)

    warnings = json.loads((c.dir / "bake" / "scene.json").read_text()).get("warnings", [])
    padding = [w for w in warnings if "pad" in w.lower()]
    c.expect("bake: no warning about the padding", padding or "none", "none", not padding)


if __name__ == "__main__":
    Check.main(run, "delay")
