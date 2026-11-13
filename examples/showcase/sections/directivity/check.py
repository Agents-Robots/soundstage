"""Known answers of ``directivity`` (README.md), asserted on the pink-noise probes at the left intake
(the whine's cone) and the left nozzle (the roar's cone): the level of `cones` against `omni` at the
same time, which leaves the cone alone, against the cone formula at the angle from the baked
positions; the spectrum unchanged by a cone; the stems.

    .venv/bin/python examples/showcase/sections/directivity/check.py [--dir out/showcase/directivity]
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from kit import measure  # noqa: E402
from kit.checks import Check  # noqa: E402
from section import FADE_IN_S, FADE_OUT_S, LAP_S, beta, camera_position, cone_at  # noqa: E402

FPS = 30
WINDOW_S = 0.2
NOMINAL = {"whine": (0.0, -7.6, -18.0), "roar": (-12.0, -4.1, 0.0)}
"""README.md: in front of the nose, abeam (90 degrees from the cone's axis), behind the tail."""


def third_octaves_db(x: np.ndarray, rate: int, centres: list[float]) -> np.ndarray:
    m = measure.mono(x)
    return np.array([measure.band_db(m, rate, c / 2 ** (1 / 6), c * 2 ** (1 / 6)) for c in centres])


def run(c: Check) -> None:
    rate = c.rate
    probe = {k: {s: c.probe(k, name).audio for s, name in (("whine", "intake"), ("roar", "exhaust"))}
             for k in ("omni", "cones")}
    first = c.windows["cones"][0]
    noise = sf.read(c.dir.parents[0] / "sounds" / "noise_pink.wav")[0]
    end = LAP_S - FADE_OUT_S - 0.6  # before the fade-out (and the sound's travel)

    def level(k: str, sound: str, t: float) -> float:
        x = probe[k][sound]
        return measure.rms_db(x[c.t(k, t - WINDOW_S / 2):c.t(k, t + WINDOW_S / 2)])

    def expected(sound: str, t: float) -> float:
        """The cone at the angle from the baked positions, averaged over the window as heard."""
        sid = f"directivity.probe.cones.{'intake' if sound == 'whine' else 'exhaust'}"
        fs = np.linspace(c.frame("cones", t - WINDOW_S / 2), c.frame("cones", t + WINDOW_S / 2), 9)
        omni = [c.geo.direct_gain_db(sid.replace("cones", "omni"), f - first + c.windows["omni"][0]) for f in fs]
        cones = [c.geo.direct_gain_db(sid, f) for f in fs]
        return 10 * np.log10(np.mean(10 ** (np.array(cones) / 10)) / np.mean(10 ** (np.array(omni) / 10)))

    for sound in ("whine", "roar"):
        name = "intake" if sound == "whine" else "exhaust"
        # in front of the nose, abeam (the time at which the angle to the cone's axis is 90 degrees),
        # behind the tail
        ts = np.linspace(FADE_IN_S + 0.2, LAP_S / 2, 2000)
        abeam = ts[np.argmin([abs(beta(sound, -1, camera_position(t)) - 90) for t in ts])]
        for label, t, nominal in zip(("in front of the nose", "abeam", "behind the tail"),
                                     (FADE_IN_S + 0.3, abeam, LAP_S / 2), NOMINAL[sound]):
            got = level("cones", sound, t) - level("omni", sound, t)
            c.near(f"{name} probe, camera {label} ({t:.2f} s), cones minus omni", got, expected(sound, t), 0.7, "dB", 2)
            c.near(f"{name} probe, camera {label}, against README.md", got, nominal, 0.7, "dB", 2)
        ts = np.arange(FADE_IN_S + 0.3, end, 0.1)
        err = [level("cones", sound, t) - level("omni", sound, t) - expected(sound, t) for t in ts]
        worst = float(np.max(np.abs(err)))
        c.expect(f"{name} probe: whole lap against the cone formula ({len(ts)} windows)", f"max {worst:.2f} dB",
                 "within 0.5 dB", worst <= 0.5)
        # omni: the level follows the distance alone; measured against the part of the noise sample
        # emitted for each window, so that the noise's own fluctuation cancels
        sid = f"directivity.probe.omni.{name}"
        rest = []
        for t in ts:
            f = c.frame("omni", t)
            te = (c.geo.emission(sid, f) - c.windows["omni"][0]) / FPS
            a = int(round((te - WINDOW_S / 2) * rate))
            emitted = noise[np.arange(a, a + int(WINDOW_S * rate)) % len(noise)]
            rest.append(level("omni", sound, t) - measure.rms_db(emitted) - c.geo.direct_gain_db(sid, f))
        spread = (max(rest) - min(rest)) / 2
        c.expect(f"{name} probe, omni: level over the lap less the distance law", f"± {spread:.2f} dB",
                 "constant within ± 0.3 dB", spread <= 0.3)
        # a cone is broadband: where its gain is steady over the window (it changes with the angle
        # elsewhere, and the noise's spectrum with time), cones and omni differ by one gain at all bands
        centres = [125, 250, 500, 1000, 2000, 4000, 8000]
        steady = [t for t in np.arange(FADE_IN_S + 0.5, end, 0.05)
                  if abs(cone_at(sound, -1, t + 0.25) - cone_at(sound, -1, t - 0.25)) < 0.05]
        groups: dict[float, list[float]] = {}
        for t in steady:
            groups.setdefault(round(cone_at(sound, -1, t), 1), []).append(t)
        picks = [ts_[i] for ts_ in groups.values() for i in np.linspace(0, len(ts_) - 1, 5).astype(int)]
        gains = sorted(groups)
        shape = 0.0
        for t in picks:
            a, b = (probe[k][sound][c.t(k, t - 0.25):c.t(k, t + 0.25)] for k in ("cones", "omni"))
            d = third_octaves_db(a, rate, centres) - third_octaves_db(b, rate, centres)
            shape = max(shape, float(np.ptp(d)))
        c.expect(f"{name} probe: spectrum cones against omni, 125 Hz to 8 kHz, {len(picks)} angles (cone {gains} dB)",
                 f"spread {shape:.2f} dB",
                 "within 0.2 dB (a cone is broadband)", shape <= 0.2)

    for k in ("omni", "cones"):
        rates = [r for s in c.pass_report(k)["sources"] if not s["id"].startswith("directivity.probe")
                 for r in s["rate"]]
        c.expect(f"{k}: playback rate (R1)", f"{min(rates):.4f} to {max(rates):.4f}", "1 ± 0.005",
                 max(abs(r - 1) for r in rates) <= 0.005)
        mix = c.pass_audio(k)
        stems = c.stem(k, "intake") + c.stem(k, "exhaust")
        d = float(np.max(np.abs(stems - mix)))
        c.expect(f"{k}: stems intake + exhaust = mix", f"max {d:.1e}", "within 1e-6", d <= 1e-6)


if __name__ == "__main__":
    Check.main(run, "directivity")
