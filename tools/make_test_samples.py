"""Generate the synthetic test and placeholder samples in samples/ (run in the repo venv).

Deterministic: the same files on every run. Periodic sounds are synthesized in the frequency
domain or with whole numbers of cycles, so they loop without a seam.

Output (48 kHz, 24-bit PCM unless stated):

- ``sine_1k.wav``: 1 kHz sine, 4 s, seamless loop.
- ``sine_1k_44k1.wav``: the same at 44.1 kHz (resampling tests).
- ``click.wav``: single-sample impulse followed by silence, 1 s.
- ``noise_pink.wav``: pink noise, 4 s, seamless loop.
- ``engine_hum.wav``: harmonic hum with slow modulation and rumble, 6 s, seamless loop.
- ``beep.wav``: 2 kHz tone burst, 0.15 s.
- ``impact.wav``: low thump plus decaying noise burst, 1.5 s.
- ``whoosh.wav``: swelling band-limited noise, 1.6 s.
- ``ambience_stereo.wav``: low decorrelated stereo noise bed, 8 s, seamless loop.

Usage: ``.venv/bin/python tools/make_test_samples.py [--out samples/]``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf

RATE = 48000


def periodic_noise(n: int, rng: np.random.Generator, shape) -> np.ndarray:
    """Noise of length n that loops seamlessly, with spectral magnitude shape(f)."""
    f = np.fft.rfftfreq(n, 1 / RATE)
    spec = shape(f) * np.exp(2j * np.pi * rng.random(len(f)))
    spec[0] = 0
    x = np.fft.irfft(spec, n)
    return x / np.abs(x).max()


def pink(f: np.ndarray) -> np.ndarray:
    return np.where(f > 20, 1 / np.sqrt(np.maximum(f, 1)), 0.0)


def normalize(x: np.ndarray, peak_db: float = -1.0) -> np.ndarray:
    return x / np.abs(x).max() * 10 ** (peak_db / 20)


def fade(x: np.ndarray, fade_in: float, fade_out: float) -> np.ndarray:
    x = x.copy()
    a, b = int(fade_in * RATE), int(fade_out * RATE)
    if a:
        x[:a] *= np.sin(0.5 * np.pi * np.arange(a) / a) ** 2
    if b:
        x[-b:] *= np.cos(0.5 * np.pi * np.arange(b) / b) ** 2
    return x


def make(out: Path) -> list[Path]:
    rng = np.random.default_rng(20261025)
    t = lambda seconds: np.arange(int(seconds * RATE)) / RATE  # noqa: E731
    files: dict[str, tuple[np.ndarray, int]] = {}

    files["sine_1k.wav"] = (0.5 * np.sin(2 * np.pi * 1000 * t(4)), RATE)
    files["sine_1k_44k1.wav"] = (0.5 * np.sin(2 * np.pi * 1000 * np.arange(4 * 44100) / 44100), 44100)

    click = np.zeros(RATE)
    click[0] = 0.9
    files["click.wav"] = (click, RATE)

    files["noise_pink.wav"] = (normalize(periodic_noise(4 * RATE, rng, pink), -3), RATE)

    # Engine hum: every frequency is a whole number of cycles in 6 s, so the loop is seamless.
    tt = t(6)
    hum = sum(a * np.sin(2 * np.pi * 55 * k * tt + k) for k, a in [(1, 1.0), (2, 0.6), (3, 0.35), (4, 0.25), (6, 0.12)])
    hum *= 1 + 0.15 * np.sin(2 * np.pi * 0.5 * tt)
    rumble = periodic_noise(len(tt), rng, lambda f: np.where((f > 30) & (f < 400), 1 / np.maximum(f, 1), 0.0))
    hiss = periodic_noise(len(tt), rng, lambda f: np.exp(-(((f - 3000) / 1500) ** 2)))
    files["engine_hum.wav"] = (normalize(hum / 2.3 + 0.5 * rumble + 0.08 * hiss), RATE)

    beep = np.sin(2 * np.pi * 2000 * t(0.15))
    files["beep.wav"] = (normalize(fade(beep, 0.005, 0.03), -3), RATE)

    ti = t(1.5)
    thump = np.sin(2 * np.pi * np.cumsum(40 + 80 * np.exp(-ti / 0.05)) / RATE) * np.exp(-ti / 0.25)
    crack = rng.standard_normal(len(ti)) * np.exp(-ti / 0.08)
    files["impact.wav"] = (normalize(fade(thump + 0.5 * crack, 0.0005, 0.2)), RATE)

    tw = t(1.6)
    sweep = periodic_noise(len(tw), rng, lambda f: np.exp(-(((f - 900) / 700) ** 2)) + 0.3 * pink(f) * 30)
    files["whoosh.wav"] = (normalize(sweep * np.sin(np.pi * tw / tw[-1]) ** 3), RATE)

    left = periodic_noise(8 * RATE, rng, lambda f: pink(f) * np.exp(-f / 4000))
    right = periodic_noise(8 * RATE, rng, lambda f: pink(f) * np.exp(-f / 4000))
    files["ambience_stereo.wav"] = (normalize(np.stack([left, right], axis=1), -12), RATE)

    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, (data, rate) in files.items():
        path = out / name
        sf.write(path, data, rate, subtype="PCM_24")
        written.append(path)
    return written


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "samples"))
    for path in make(Path(p.parse_args().out)):
        print(path)


if __name__ == "__main__":
    main()
