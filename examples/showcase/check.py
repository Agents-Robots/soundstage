"""Known-answer checks on the showcase pass renders (runs in the repo venv, after ``audio.py``).

Each check measures one pass WAV in ``<out>/passes/`` against the value the feature should produce
(levels per doubling of distance, arrival times, Doppler frequencies, air absorption per band,
interaural lag, cone and rear gains, occlusion loss, reverb decay and direct-to-reverberant ratio,
camera cuts). Event times come from the baked scene file, so the checks follow the storyboard.

    .venv/bin/python examples/showcase/check.py [--out out/showcase]

Prints one line per measurement and exits 1 if any is outside its tolerance.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import storyboard as sb  # noqa: E402

from soundstage.engine import filters  # noqa: E402

C = 343.0
results: list[tuple[str, float, float, float, bool]] = []


def expect(name: str, measured: float, expected: float, tolerance: float) -> None:
    ok = bool(abs(measured - expected) <= tolerance)
    results.append((name, measured, expected, tolerance, ok))
    print(f"{'ok  ' if ok else 'FAIL'} {name:58s} {measured:9.3f}  expected {expected:9.3f} ± {tolerance:g}")


class Pass:
    """A pass render: its audio from the pass's first frame, its report and its sources' tags."""

    def __init__(self, out: Path, chapter: str, key: str, sources: dict):
        self.audio, self.rate = sf.read(out / "passes" / f"{chapter}.{key}.wav")
        self.report = json.loads((out / "passes" / f"{chapter}.{key}.report.json").read_text())
        self.first = sb.timeline()[chapter].passes[key].first
        self.tags = {i.split(".", 2)[2]: s for i, s in sources.items() if i.startswith(f"{chapter}.{key}.")}
        self.stats = {s["id"].split(".", 2)[2]: s for s in self.report["sources"]}

    def t(self, frame: float) -> float:
        """Seconds from the start of the pass."""
        return (frame - self.first) / sb.FPS

    def cut(self, a: float, b: float, channel: int | None = None) -> np.ndarray:
        x = self.audio[int(round(a * self.rate)):int(round(b * self.rate))]
        return x if channel is None else x[:, channel]


def power_db(x: np.ndarray) -> float:
    return float(10 * np.log10(np.mean(np.square(x)) + 1e-30))


def band_db(x: np.ndarray, rate: int, f: float) -> float:
    """Power in the third-octave band around f (summed over channels)."""
    x = x if x.ndim == 2 else x[:, None]
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))[:, None], axis=0)) ** 2
    freqs = np.fft.rfftfreq(len(x), 1 / rate)
    band = (freqs >= f * 2 ** (-1 / 6)) & (freqs < f * 2 ** (1 / 6))
    return float(10 * np.log10(spec[band].sum() + 1e-30))


def onset(x: np.ndarray, rate: int, start: float, threshold: float = 0.2) -> float:
    """First time after ``start`` where the signal exceeds ``threshold`` x its peak there."""
    mono = np.abs(x).max(axis=1)
    i0 = int(start * rate)
    seg = mono[i0:i0 + int(0.6 * rate)]
    return (i0 + int(np.argmax(seg > threshold * seg.max()))) / rate


def frequency(x: np.ndarray, rate: int) -> float:
    """Frequency of a sine from sub-sample zero crossings."""
    z = np.nonzero((x[:-1] <= 0) & (x[1:] > 0))[0]
    t = z + x[z] / (x[z] - x[z + 1])
    return (len(t) - 1) / ((t[-1] - t[0]) / rate)


def lag_samples(left: np.ndarray, right: np.ndarray, max_lag: int = 64) -> float:
    """Delay of the right channel against the left (negative: right first), sub-sample by parabola."""
    lags = np.arange(-max_lag, max_lag + 1)
    c = np.array([np.dot(left[max_lag:-max_lag], np.roll(right, -k)[max_lag:-max_lag]) for k in lags])
    i = int(np.argmax(c))
    if 0 < i < len(c) - 1:
        a, b, d = c[i - 1], c[i], c[i + 1]
        return float(lags[i] + 0.5 * (a - d) / (a - 2 * b + d))
    return float(lags[i])


def check_sources(P):
    p = P("sources", "once")
    for i, f in enumerate(p.tags["ball"]["frame"][:3]):
        expect(f"sources.once: beep {i} onset (s, 6 m away)", onset(p.audio, p.rate, p.t(f) - 0.05), p.t(f) + 6 / C,
               0.003)
    p = P("sources", "pitch")
    for i, pitch in enumerate((0.5, 1.0, 2.0)):
        tag = p.tags[f"cube{i}"]
        a, b = p.t(tag["frame"]) + 0.3, p.t(tag["end_frame"]) - 0.1
        expect(f"sources.pitch: cube {i} frequency (Hz)", frequency(p.cut(a, b).sum(axis=1), p.rate), 1000 * pitch, 0.5)


def check_distance(P):
    """Both passes play the loop from the same point (loop_phase 0): on minus off is the distance
    gain alone. The off pass is flat apart from the pan and head shadow (300 Hz to 1.5 kHz)."""
    off, on = P("distance", "off"), P("distance", "on")
    start = off.t(off.tags["sphere"]["frame"]) + 0.1  # hold k: 0.5 + 1.35 k .. + 1.0 s

    def hold(p, k, lo=20.0, hi=20000.0):
        return band_power_db(p.cut(start + 1.35 * k + 0.05, start + 1.35 * k + 0.95), p.rate, lo, hi)

    gain = [hold(on, k) - hold(off, k) for k in range(6)]
    for k in range(1, 6):
        expect(f"distance.on: gain change {2 ** k} m -> {2 ** (k + 1)} m (dB)", gain[k] - gain[k - 1], -6.02, 0.2)
    flat = [hold(off, k, 300, 1500) for k in range(6)]
    expect("distance.off: largest level change between posts (dB)", max(flat) - min(flat), 0.0, 0.6)


def band_power_db(x: np.ndarray, rate: int, lo: float, hi: float) -> float:
    spec = np.abs(np.fft.rfft(x, axis=0)) ** 2
    freqs = np.fft.rfftfreq(len(x), 1 / rate)
    return float(10 * np.log10(spec[(freqs >= lo) & (freqs < hi)].sum() + 1e-30))


def check_screen(P):
    def ild(p, f):  # left minus right channel (dB) of the left shape's burst at frame f, 20 m away
        x = p.cut(p.t(f) + 20 / C, p.t(f) + 20 / C + 0.1)
        return power_db(x[:, 0]) - power_db(x[:, 1])

    cam, scr = P("screen", "camera"), P("screen", "screen")
    wide, zoomed = (cam.tags["left"]["frame"][i] for i in (0, -1))
    expect("screen.camera: level difference zoomed vs wide (dB)", ild(cam, zoomed) - ild(cam, wide), 0.0, 0.5)
    expect("screen.screen: level difference zoomed minus wide > 3 dB (1 = yes)",
           float(ild(scr, scr.tags["left"]["frame"][-1]) - ild(scr, scr.tags["left"]["frame"][0]) > 3), 1.0, 0.0)


def check_delay(P):
    for key in ("physical", "synced"):
        p = P("delay", key)
        for i in range(3):
            tag, st = p.tags[f"block{i}"], p.stats[f"block{i}"]
            d = st["distance_m"][0]
            hit = p.t(tag["frame"])
            expected = hit + (0.0 if key == "synced" else d / C)
            expect(f"delay.{key}: impact {i} ({d:.0f} m) heard at (s)", onset(p.audio, p.rate, expected - 0.1), expected,
                   0.003)


def doppler_expected(p, k: float, t_r: float, x0: float) -> float:
    """1 kHz x (1 - k dtau/dt) at reception time t_r, for the straight pass 10 m from the camera
    from x0 to -x0."""
    tag = p.tags["sphere"]
    a, b = p.t(tag["frame"]), p.t(tag["end_frame"]) + tag["fade_out"]  # the motion ends with the fade-out
    v = (-2 * x0) / (b - a)

    def tau(t):
        te = t
        for _ in range(50):
            x = x0 + v * (min(max(te, a), b) - a)
            te = t - math.hypot(x, 10) / C
        return t - te

    h = 1e-4
    return 1000 * (1 - k * (tau(t_r + h) - tau(t_r - h)) / (2 * h))


def check_doppler(P):
    for i, (key, k) in enumerate((("off", 0.0), ("on", 1.0), ("double", 2.0))):
        p = P("doppler", key)
        a = p.t(p.tags["sphere"]["frame"])
        for label, s in (("approaching", 1.5), ("receding", 5.0)):
            t_r = a + s
            f = frequency(p.cut(t_r - 0.05, t_r + 0.05).sum(axis=1), p.rate)
            expect(f"doppler.{key}: {label} at +{s:g} s (Hz)", f, doppler_expected(p, k, t_r, -100 if i % 2 == 0 else 100), 2.0)


def check_air(P):
    off, on = P("air", "off"), P("air", "on")
    alpha = filters.iso9613_alpha(np.array([1000.0, 4000.0, 8000.0]))
    for i in range(4):
        d = on.stats[f"pillar{i}"]["distance_m"][0]
        x_off = off.cut(off.t(off.tags[f"pillar{i}"]["frame"]) + 0.05, off.t(off.tags[f"pillar{i}"]["frame"]) + 0.75)
        x_on = on.cut(on.t(on.tags[f"pillar{i}"]["frame"]) + 0.05, on.t(on.tags[f"pillar{i}"]["frame"]) + 0.75)
        for f, a in zip((1000.0, 4000.0, 8000.0), alpha):
            loss = band_db(x_off, off.rate, f) - band_db(x_on, on.rate, f)
            expect(f"air: {d:.0f} m, loss at {f / 1000:g} kHz (dB)", loss, a * d, max(1.0, 0.1 * a * d))


def check_ears(P):
    for key, scale in (("amplitude", 0.0), ("hybrid", 0.5), ("full", 1.0)):
        p = P("ears", key)
        f = p.tags["sphere"]["frame"][6]  # 1.5 s into the orbit: 90° to the right
        a = p.t(f) + 5 / C
        x = p.cut(a - 0.005, a + 0.1)
        itd = scale * 0.0875 / C * (math.pi / 2 + 1)
        expect(f"ears.{key}: right ear leads by (samples)", -lag_samples(x[:, 0], x[:, 1]), itd * p.rate, 1.5)


def check_rear(P):
    """All three passes play the same noise (loop_phase 0): each against rear-off at the same moment,
    in front (15° left) and behind (±6°), 300 to 700 Hz (below both cutoffs)."""
    off = P("rear", "off")
    a = off.t(off.tags["sphere"]["frame"]) + 5 / C
    for key, behind in (("default", -2.0), ("strong", -6.0 - 10 * math.log10(1 + (500 / 2000) ** 2))):
        p = P("rear", key)
        for where, t, expected in (("in front", 5.75, 0.0), ("behind", 3.0, behind)):
            x, ref = p.cut(a + t - 0.1, a + t + 0.1), off.cut(a + t - 0.1, a + t + 0.1)
            expect(f"rear.{key}: {where}, against rear cue off (dB)",
                   band_power_db(x, p.rate, 300, 700) - band_power_db(ref, p.rate, 300, 700), expected, 0.3)


def check_cone(P):
    for key, gain in (("omni", 0.0), ("cone", -24.0)):
        p = P("cone", key)
        a = p.t(p.tags["horn"]["frame"]) + 0.2  # the turn starts 0.2 s after the sound
        expect(f"cone.{key}: facing away vs facing the camera (dB)",
               power_db(p.cut(a + 2.85, a + 3.15)) - power_db(p.cut(a + 5.7, a + 5.95)), gain, 1.0)


def check_occlusion(P):
    off, on = P("occlusion", "off"), P("occlusion", "on")
    a = off.t(off.tags["sphere"]["frame"]) + 0.2
    visibility = on.stats["sphere"]["visibility"]
    for f, expected, tol in ((250.0, -12.1, 1.5), (4000.0, -20.9, 3.0)):
        x_off, x_on = off.cut(a + 2.8, a + 3.2), on.cut(a + 2.8, a + 3.2)
        expect(f"occlusion: behind the wall, {f:g} Hz on vs off (dB)", band_db(x_on, on.rate, f) - band_db(x_off, off.rate, f),
               expected, tol)
    expect("occlusion: least visibility over the pass", visibility[0], 0.0, 0.05)


def decay_time(x: np.ndarray, rate: int) -> float:
    """T20 from the Schroeder curve (-5 to -25 dB), extrapolated to 60 dB."""
    e = np.cumsum(np.square(x).sum(axis=1)[::-1])[::-1]
    db = 10 * np.log10(e / e[0] + 1e-30)
    i5, i25 = int(np.argmax(db < -5)), int(np.argmax(db < -25))
    return 3.0 * (i25 - i5) / rate


def check_reverb(P, out: Path):
    share = {}
    for key, decay in (("room", 0.40), ("alley", 1.49), ("hall", 3.92)):
        p = P("reverb", key)
        wet, _ = sf.read(out / "passes" / f"reverb.{key}_stem_reverb.wav")
        share[key] = power_db(wet) - power_db(p.audio)
        if key == "hall":  # longer than the impact's own decay (about 1.7 s), so it shows in the return
            last = p.t(p.tags["ball"]["frame"][-1])
            expect("reverb.hall: decay time T20 of the return (s)", decay_time(wet[int((last + 0.3) * p.rate):], p.rate),
                   decay, 0.3 * decay)
    print("     reverb return against the whole pass (dB): " + ", ".join(f"{k} {v:.1f}" for k, v in share.items()))
    p = P("reverb", "far")
    wet, _ = sf.read(out / "passes" / "reverb.far_stem_reverb.wav")
    dry = p.audio - wet
    first, last = (p.t(p.tags["ball"]["frame"][i]) for i in (0, -1))
    d0, d1 = (math.hypot(y, 1.3) for y in (3.0, 60.0))
    expected = 20 * math.log10(5 / d1) - 20 * math.log10(min(1.0, 5 / d0))
    expect("reverb.far: direct sound, last hop vs first (dB)",
           power_db(dry[int(last * p.rate):int((last + 0.35) * p.rate)]) - power_db(dry[int(first * p.rate):int((first + 0.35) * p.rate)]),
           expected, 1.0)


def check_cuts(P):
    p = P("cuts", "cuts")
    last = p.first + round(len(p.audio) / p.rate * sb.FPS) - 1
    cuts = [c for c in p.report["cuts"] if p.first < c <= last]
    expect("cuts: cuts inside the pass", len(cuts), 3, 0)
    rate = p.stats["cube"]["rate"]
    expect("cuts: largest playback-rate deviation (no glide)", max(abs(rate[0] - 1), abs(rate[1] - 1)), 0.0, 0.006)
    for c in cuts:
        t = p.t(c)
        jump = power_db(p.cut(t + 0.12, t + 0.42)) - power_db(p.cut(t - 0.32, t - 0.02))
        expect(f"cuts: level jump at frame {c:g}, |dB| > 6 (1 = yes)", float(abs(jump) > 6), 1.0, 0.0)


def check_mix(out: Path):
    rep = json.loads((out / "showcase.report.json").read_text())
    expect("mix: true peak at most -1 dBTP (1 = yes)", float(rep["master"]["true_peak_dbtp"] <= -1.0), 1.0, 0.0)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="out/showcase")
    p.add_argument("--scene", default="out/showcase/bake/scene.json")
    a = p.parse_args()
    out = Path(a.out)
    sources = {s["id"]: s for s in json.loads(Path(a.scene).read_text())["sources"]}

    def P(chapter, key):
        return Pass(out, chapter, key, sources)

    for fn in (check_sources, check_distance, check_screen, check_delay, check_doppler, check_air, check_ears, check_rear,
               check_cone, check_occlusion, check_cuts):
        fn(P)
    check_reverb(P, out)
    check_mix(out)
    failed = [r for r in results if not r[4]]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
