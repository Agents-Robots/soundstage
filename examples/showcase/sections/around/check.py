"""Known answers of ``around`` (README.md), asserted on the pink-noise probe on the scooter: channel
power and balance, the lag between the channels, head shadow, and the rear cue: on the lap as shown,
and on the lap rendered for the checks with level difference only and without the rear cue.

Levels and spectra are measured against the part of the probe sample that was emitted for each
window (its loop starts on the pass's first frame), so that the noise's own fluctuation cancels and
only the engine's gains and filters remain.

    .venv/bin/python examples/showcase/sections/around/check.py [--dir out/showcase/around]
"""

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from kit.checks import C, Check  # noqa: E402
from section import (  # noqa: E402
    AMPLITUDE,
    HYBRID,
    ILD_LIMIT_DB,
    LAP_S,
    RADIUS,
    REAR_DEFAULTS,
    REAR_OFF,
    itd_ms,
    rear_db,
    rear_factor,
)

from soundstage.engine.propagation import interpolator_for  # noqa: E402

DELAY_S = math.hypot(RADIUS, 0.6) / C


def at_angle(deg: float) -> float:
    """Seconds into a pass at which the sound emitted at that angle (clockwise from ahead) is heard."""
    return deg / 360 * LAP_S + DELAY_S


def window(x: np.ndarray, rate: int, centre_s: float, length_s: float) -> np.ndarray:
    a = int(round((centre_s - length_s / 2) * rate))
    return x[a:a + int(round(length_s * rate))]


def emitted(sample: np.ndarray, rate: int, centre_s: float, length_s: float) -> np.ndarray:
    """The probe sample that the window around centre_s (heard) carries."""
    a = int(round((centre_s - DELAY_S - length_s / 2) * rate))
    return sample[np.arange(a, a + int(round(length_s * rate))) % len(sample)]


def bands_db(x: np.ndarray, rate: int, centres: list[float], fraction: float = 1 / 3) -> np.ndarray:
    """Power (dB) in bands of ``fraction`` octave around each centre, summed over the channels."""
    x = x if x.ndim == 2 else x[:, None]
    spec = (np.abs(np.fft.rfft(x * np.hanning(len(x))[:, None], axis=0)) ** 2).sum(axis=1)
    f = np.fft.rfftfreq(len(x), 1 / rate)
    k = 2 ** (fraction / 2)
    return np.array([10 * np.log10(spec[(f >= c / k) & (f < c * k)].sum()) for c in centres])


def lag_samples(x: np.ndarray) -> float:
    """Lag of the left channel behind the right (samples, positive when the right is first), from the
    peak of their cross-correlation with parabolic refinement."""
    left, right = x[:, 0], x[:, 1]
    n = 1 << int(np.ceil(np.log2(2 * len(x))))
    cc = np.fft.irfft(np.fft.rfft(left, n) * np.conj(np.fft.rfft(right, n)), n)
    cc = np.concatenate([cc[-64:], cc[:65]])  # lags -64 ... 64
    i = int(np.argmax(cc))
    a, b, c = cc[i - 1:i + 2]
    return i - 64 + 0.5 * (a - c) / (a - 2 * b + c)


def band_response(x: np.ndarray, rate: int, fc: float, rho: float, gain_db: float, cutoff_hz: float, fe: int) -> float:
    """The rear cue's effect on a third octave around fc (dB), weighted by x's spectrum in it."""
    x = x if x.ndim == 2 else x[:, None]
    p = (np.abs(np.fft.rfft(x * np.hanning(len(x))[:, None], axis=0)) ** 2).sum(axis=1)
    f = np.fft.rfftfreq(len(x), 1 / rate)
    sel = (f >= fc / 2 ** (1 / 6)) & (f < fc * 2 ** (1 / 6))
    h = np.array([10 ** (rear_db(v, rho, gain_db, cutoff_hz, rate=fe) / 10) for v in f[sel]])
    return float(10 * np.log10(np.sum(p[sel] * h) / np.sum(p[sel])))


def run(c: Check) -> None:
    rate = c.rate
    sample, _ = sf.read(c.dir.parents[0] / "sounds" / "noise_pink.wav")
    # the lap as shown (`rear`: the full ear model), and rendered for these checks only with level
    # difference only (`amplitude`) and with the ear model but no rear cue (`hybrid`)
    probe = {"amplitude": c.probe("lap", "noise", extra=AMPLITUDE).audio,
             "hybrid": c.probe("lap", "noise", extra=HYBRID).audio, "rear": c.probe("lap", "noise").audio}

    rates = [s["rate"] for s in c.pass_report("lap")["sources"] if s["id"] == "around.lap.engine"][0]
    c.expect("lap: playback rate (R1)", f"{rates[0]:.4f} to {rates[1]:.4f}", "1.000 ± 0.001",
             abs(rates[0] - 1) <= 1e-3 and abs(rates[1] - 1) <= 1e-3)

    # amplitude: constant power around the lap, nothing in the far ear, no lag
    # constant power: windows 4 s (one loop of the noise, 120 degrees) apart carry the same noise, so
    # their difference is the pan alone
    x = probe["amplitude"]
    loop_s = len(sample) / rate
    steps = []
    for t in np.arange(0.6, LAP_S - 0.9 - 2 * loop_s, 0.25):
        power = [np.sum(window(x, rate, t + k * loop_s, 0.4) ** 2) for k in range(3)]
        steps += [10 * np.log10(power[k] / power[0]) for k in (1, 2)]
    worst = float(np.max(np.abs(steps)))
    c.expect(f"amplitude: power of both channels around the lap ({len(steps)} pairs 120 and 240 degrees apart)",
             f"max {worst:.3f} dB", "within 0.1 dB", worst <= 0.1)
    side = window(x, rate, at_angle(90), 0.1)
    sep = 10 * np.log10(np.sum(side[:, 0] ** 2) / np.sum(side[:, 1] ** 2))
    c.expect("amplitude: right (3 s), left channel against right", f"{sep:.1f} dB", "40 dB or more below", sep <= -40)
    lags = [lag_samples(window(x, rate, at_angle(a), 0.2)) for a in range(15, 346, 30)]
    worst = max(lags, key=abs)
    c.expect("amplitude: lag between the channels, every 30 degrees", f"max {worst:+.2f} samples", "0 ± 0.5",
             abs(worst) <= 0.5)

    # hybrid: time difference at the sides, right first on the right
    x = probe["hybrid"]
    for deg, name in ((90, "right (3 s)"), (270, "left (9 s)")):
        t = at_angle(deg)
        want = itd_ms(t - DELAY_S) * rate / 1000
        c.near(f"hybrid: lag at the {name}, positive when the right ear is first", lag_samples(window(x, rate, t, 0.2)),
               want, 1.0, "samples", 2)
    # the far ear at the sides: 12 dB below the near one (ild_limit_db), not silent as in `amplitude`;
    # in the 125 Hz octave, where the head shadow adds less than 0.1 dB
    for deg, name, sign in ((90, "right (3 s)", 1), (270, "left (9 s)", -1)):
        w = window(x, rate, at_angle(deg), 0.2)
        near_far = sign * float(bands_db(w[:, 1:], rate, [125], 1)[0] - bands_db(w[:, :1], rate, [125], 1)[0])
        c.near(f"hybrid: {name}, near ear minus far ear, 125 Hz octave (ild_limit_db)", near_far, ILD_LIMIT_DB + 0.1,
               0.5, "dB", 2)
    # head shadow on the right: the far (left) ear is duller than the near one. At 60 degrees (2 s),
    # where the far channel of `amplitude` is 15 dB down: at 90 degrees it is more than 40 dB down and
    # no longer a clean copy of the near one. A short window, so that the pan gains hardly change in it
    for k in ("amplitude", "hybrid"):
        w = window(probe[k], rate, at_angle(60), 0.1)
        left = bands_db(w[:, :1], rate, [250, 4000], 1)
        right = bands_db(w[:, 1:], rate, [250, 4000], 1)
        tilt = (left[1] - left[0]) - (right[1] - right[0])
        if k == "hybrid":
            c.expect("hybrid: right (2 s), far ear against near ear, 4 kHz minus 250 Hz octave", f"{tilt:+.1f} dB",
                     "negative (head shadow)", tilt < -1.0)
        else:
            c.expect("amplitude: the same, no head shadow", f"{tilt:+.2f} dB", "0 ± 0.2", abs(tilt) <= 0.2)

    # front and behind (mirror positions, 15 and 165 degrees: the same pan and head shadow). `hybrid`
    # keeps the rear low-pass at its highest cutoff (20 kHz, rear_gain_db=0): it cannot be switched off,
    # and behind it takes about 1 dB off 12 kHz
    fe = rate * interpolator_for("standard").oversample
    centres = [250, 500, 1000, 2000, 4000, 6000, 8000, 12000]
    for k in ("amplitude", "hybrid"):
        diff, x_back = [], None
        for deg in (15, 165):
            t = at_angle(deg)
            out, inp = window(probe[k], rate, t, 0.25), emitted(sample, rate, t, 0.25)
            diff.append(bands_db(out, rate, centres) - bands_db(inp, rate, centres))
            x_back = inp
        rho = rear_factor(at_angle(165) - DELAY_S) if k == "hybrid" else 0.0
        want = np.array([band_response(x_back, rate, fc, rho, 0.0, REAR_OFF["rear_cutoff_hz"], fe) for fc in centres])
        worst = float(np.max(np.abs(diff[1] - diff[0] - want)))
        c.expect(f"{k}: behind (165 degrees) against in front (15), 1/3 octaves 250 Hz to 12 kHz"
                 + (", less the 20 kHz rear low-pass" if k == "hybrid" else ""), f"max {worst:.3f} dB",
                 "within 0.2 dB", worst <= 0.2)

    # the rear cue: rear minus hybrid, the same input in both renders; expected over each third octave,
    # weighted by the spectrum there (the cue's slope is steep at 12 kHz), less the hybrid render's own
    # 20 kHz low-pass
    t = at_angle(180)
    rho = rear_factor(t - DELAY_S)
    rear, hyb = window(probe["rear"], rate, t, 0.3), window(probe["hybrid"], rate, t, 0.3)
    for fc in (1000, 6000, 12000):
        got = bands_db(rear, rate, [fc])[0] - bands_db(hyb, rate, [fc])[0]
        want = band_response(hyb, rate, fc, rho, *REAR_DEFAULTS, fe) - \
            band_response(hyb, rate, fc, rho, 0.0, REAR_OFF["rear_cutoff_hz"], fe)
        c.near(f"rear minus hybrid, behind (6 s), {fc / 1000:g} kHz third octave", got, want, 0.7, "dB", 2)
    worst = 0.0
    for deg, length in ((20, 0.3), (84, 0.12), (276, 0.12), (340, 0.3)):
        d = bands_db(window(probe["rear"], rate, at_angle(deg), length), rate, centres) - \
            bands_db(window(probe["hybrid"], rate, at_angle(deg), length), rate, centres)
        worst = max(worst, float(np.max(np.abs(d))))
    c.expect("rear minus hybrid, in front and at the sides (20, 84, 276, 340 degrees)", f"max {worst:.3f} dB",
             "0 ± 0.1 dB", worst <= 0.1)


if __name__ == "__main__":
    Check.main(run, "around")
