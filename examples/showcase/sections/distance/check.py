"""Known answers of ``distance`` (README.md), asserted on the probes: level per camera, the air's loss
per band against ISO 9613-1, click arrival times, playback rate.

    .venv/bin/python examples/showcase/sections/distance/check.py [--dir out/showcase/distance]
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from kit import measure, story  # noqa: E402
from kit.checks import C, Check  # noqa: E402
from section import BANDS_HZ, DISTANCES, LEAD_FRAMES, SHOT_FRAMES, air_alpha_db_per_m  # noqa: E402

from soundstage.engine.filters import iso9613_alpha  # noqa: E402

MEASURE_S = (0.4, 1.9)
"""Part of each 2.5 s shot that is measured: away from the cuts, and before the music's fade-out in
the last shot."""
OCTAVES = {1000: 0.5, 4000: 1.5, 8000: 2.0}
"""Octave band centre: tolerance (dB) of the air's loss."""


def shot(x: np.ndarray, i: int, rate: int, span=MEASURE_S) -> np.ndarray:
    a = i * SHOT_FRAMES * story.SAMPLES_PER_FRAME
    return measure.mono(x[a + int(span[0] * rate):a + int(span[1] * rate)])


def spectrum(x: np.ndarray, rate: int) -> tuple[np.ndarray, np.ndarray]:
    return np.fft.rfftfreq(len(x), 1 / rate), np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2


def run(c: Check) -> None:
    rate = c.rate
    sid = lambda k, n: f"distance.probe.{k}.{n}"  # noqa: E731
    first = {k: w[0] for k, w in c.windows.items()}
    mid = lambda k, i: first[k] + i * SHOT_FRAMES + SHOT_FRAMES / 2  # noqa: E731
    dist = [float(c.geo.distance(sid("air", "noise"), mid("air", i))) for i in range(5)]
    for i, (d, nominal) in enumerate(zip(dist, DISTANCES)):
        c.near(f"camera {i + 1}: distance to the music", d, nominal, 0.01, "m", 3)

    # the instruments' ISO 9613-1 coefficients are the engine's
    err = max(abs(air_alpha_db_per_m(f) / float(iso9613_alpha(np.array(f))) - 1) for f in BANDS_HZ)
    c.expect("spectrum strip: ISO 9613-1 as in the engine", f"max rel. error {err:.1e}", "below 1e-9", err < 1e-9)

    # levels relative to the part of the probe sample each camera hears (emitted d / c earlier), so
    # that the noise's own fluctuation is not counted
    sample, _ = sf.read(c.dir.parents[0] / "sounds" / "noise_pink.wav")

    def emitted(i: int) -> np.ndarray:
        """The probe sample (loop_phase 0 at the music's start) that camera i hears in its window."""
        t0 = (i * SHOT_FRAMES + LEAD_FRAMES) / story.FPS - dist[i] / C
        return sample[np.arange(int((t0 + MEASURE_S[0]) * rate), int((t0 + MEASURE_S[1]) * rate)) % len(sample)]

    noise = {k: c.probe(k, "noise").audio for k in ("none", "inverse", "air")}
    none = [measure.rms_db(shot(noise["none"], i, rate)) - measure.rms_db(emitted(i)) for i in range(5)]
    c.expect("none: probe level equal at the five cameras", f"spread {max(none) - min(none):.2f} dB", "within 0.1 dB",
             max(none) - min(none) <= 0.1)
    inv = [measure.rms_db(shot(noise["inverse"], i, rate)) - measure.rms_db(emitted(i)) for i in range(5)]
    for i, d in enumerate(dist):
        c.near(f"inverse: probe level at camera {i + 1} re camera 5", inv[i] - inv[4], 20 * np.log10(dist[4] / d), 0.3,
               "dB", 2)

    # air: the loss per octave band, against ISO 9613-1 over the band (weighted by the probe's spectrum)
    for i, d in enumerate(dist):
        f, p_inv = spectrum(shot(noise["inverse"], i, rate), rate)
        _, p_air = spectrum(shot(noise["air"], i, rate), rate)
        for fc, tol in OCTAVES.items():
            sel = (f >= fc / np.sqrt(2)) & (f < fc * np.sqrt(2))
            got = 10 * np.log10(p_air[sel].sum() / p_inv[sel].sum())
            want = 10 * np.log10(np.sum(p_inv[sel] * 10 ** (-iso9613_alpha(f[sel]) * d / 10)) / p_inv[sel].sum())
            if want < -50:
                c.expect(f"air: {fc // 1000} kHz octave at camera {i + 1} ({d:g} m)", f"{got:.1f} dB",
                         f"below -50 dB (ISO {want:.1f} dB)", got < -50)
            else:
                c.near(f"air: {fc // 1000} kHz octave at camera {i + 1} ({d:g} m)", got, want, tol, "dB", 1)

    # clicks every 2 s from the music's start: arrival after emission
    clicks = c.probe("air", "click").audio
    start = first["air"] - LEAD_FRAMES
    for i, d in enumerate(dist):
        x = shot(clicks, i, rate, (0.02, 2.48))
        a = i * SHOT_FRAMES * story.SAMPLES_PER_FRAME + int(0.02 * rate)
        k = int(np.argmax(np.abs(x)))
        t = (a + k) / rate  # seconds into the pass
        received = first["air"] + t * story.FPS
        emitted = start + 60 * round((received - start - d / C * story.FPS) / 60)
        # the arrival at the camera of this shot (the listener jumps, so solve from within the shot)
        r = mid("air", i)
        for _ in range(30):
            r = emitted + float(c.geo.distance(sid("air", "click"), emitted, r)) / C * story.FPS
        want = (r - emitted) / story.FPS
        c.near(f"air: click arrival after emission, camera {i + 1}", 1000 * (received - emitted) / story.FPS,
               1000 * want, 1.0, "ms", 2)
        c.near(f"air: delay at camera {i + 1} = distance / 343 m/s", 1000 * want, 1000 * DISTANCES[i] / C, 0.05, "ms", 2)

    for k in ("none", "inverse", "air"):
        rates = next(s["rate"] for s in c.pass_report(k)["sources"] if s["id"] == f"distance.{k}.music")
        c.expect(f"{k}: playback rate of the music", f"{rates[0]:.4f} to {rates[1]:.4f}", "1.0000",
                 abs(rates[0] - 1) < 5e-4 and abs(rates[1] - 1) < 5e-4)


if __name__ == "__main__":
    Check.main(run, "distance")
