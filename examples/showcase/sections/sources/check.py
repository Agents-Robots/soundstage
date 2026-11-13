"""Known answers of ``sources`` (README.md), asserted on the rendered passes and the probes.

    .venv/bin/python examples/showcase/sections/sources/check.py [--dir out/showcase/sources]
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from kit import measure, story  # noqa: E402
from kit.checks import Check  # noqa: E402
from section import BELL_FRAMES, HORN_FRAME, PITCH, PITCH_ALONE_S  # noqa: E402

AUDIBLE = {"loop": 1, "layers": 3, "events": 2, "bed": 2, "pitch": 6, "stems": 4}


def click_times(x: np.ndarray, rate: int, n: int, min_gap_s: float = 0.3) -> list[float]:
    """Times (s) of the n strongest isolated peaks: the arrivals of probe clicks."""
    m = np.abs(measure.mono(x))
    out = []
    m = m.copy()
    for _ in range(n):
        i = int(np.argmax(m))
        # sub-sample position from the three samples around the peak
        a, b, c = m[i - 1], m[i], m[i + 1]
        frac = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
        out.append((i + frac) / rate)
        m[max(0, i - int(min_gap_s * rate)):i + int(min_gap_s * rate)] = 0
    return sorted(out)


def run(c: Check) -> None:
    rate = c.rate
    for k, n in AUDIBLE.items():
        rep = c.pass_report(k)
        audible = sum(1 for s in rep["sources"] if s.get("audible_frames", 0) > 0)
        c.expect(f"{k}: audible sources (R1)", audible, str(n), audible == n)

    # horn and bell: heard later than their frames by their distance (R3)
    first = c.windows["layers"][0]
    got = click_times(c.probe("layers", "horn").audio, rate, 1)[0]
    want = (c.geo.arrival("sources.probe.layers.horn", HORN_FRAME) - first) / story.FPS
    c.near("horn probe onset", 1000 * got, 1000 * want, 1.0, "ms", 2)
    first = c.windows["events"][0]
    got = click_times(c.probe("events", "bell").audio, rate, 3)
    for f, g in zip(BELL_FRAMES, got):
        want = (c.geo.arrival("sources.probe.events.bell", f) - first) / story.FPS
        late = 1000 * (want - (f - first) / story.FPS)
        c.near(f"bell probe onset, strike on frame {f} ({late:.0f} ms late)", 1000 * g, 1000 * want, 1.0, "ms", 2)

    # bed: the ambience stem is the sample times its gain, whatever the camera does
    stem = c.stem("bed", "ambience")
    bed, _ = sf.read(c.dir.parents[0] / "sounds" / "town_bed.wav", always_2d=True)
    gain = 10 ** ((-18.0 + c.man["gain_db"]) / 20)
    a, b = int(0.6 * rate), len(stem) - int(1.2 * rate)
    expected = gain * bed[np.arange(a, b) % len(bed)]
    err = float(np.abs(stem[a:b] - expected).max())
    c.expect("bed: ambience stem = sample x gain, both channels", f"max error {err:.1e}", "below 1e-6", err < 1e-6)
    probe = c.probe("bed", "car").audio
    before = measure.channel_balance_db(probe[int(0.2 * rate):int(1.0 * rate)])
    after = measure.channel_balance_db(probe[int(4.0 * rate):int(4.6 * rate)])
    c.expect("bed: probe on the car, channel balance changes in the pan", f"{before:+.1f} -> {after:+.1f} dB",
             "change above 10 dB", abs(after - before) > 10)

    # pitch: one sample at three playback rates
    for name, (p, _) in PITCH.items():
        a0, a1 = PITCH_ALONE_S[name]
        x = c.probe("pitch", name).audio[int((a0 + 0.3) * rate):int((a1 - 0.2) * rate)]
        c.near(f"pitch: {name} probe at pitch {p}", measure.frequency(x, rate), 1000 * p, 0.001 * 1000 * p, "Hz", 2)

    # stems: three groups whose sum is the mix
    mix = c.pass_audio("stems")
    groups = {g: c.stem("stems", g) for g in ("vehicles", "bells", "ambience")}
    missing = [g for g, s in groups.items() if not np.any(s)]
    c.expect("stems: groups vehicles, bells, ambience", missing or "all present", "all present", not missing)
    err = float(np.abs(sum(groups.values()) - mix).max())
    c.expect("stems: sum of the stems = mix", f"max error {err:.1e}", "below 1e-6", err < 1e-6)


if __name__ == "__main__":
    Check.main(run, "sources")
