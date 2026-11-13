"""Synthesize the showcase's synthetic sounds (runs in the repo venv; sounds/README.md, "Synthesized").

Seeded and deterministic: the same files on every run. Loops are built so that they repeat without
a seam (whole numbers of cycles, noise shaped in the frequency domain over the loop's length,
events placed around a circle). Every file is 48 kHz, 24 bit, with its peak at -3 dBFS (A6).

    .venv/bin/python examples/showcase/sounds/make.py [--out out/showcase/sounds] [NAME ...]

Writes ``<out>/<name>.wav`` and ``<out>/make.json`` (length, peak, loudness, loop measures).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from kit import measure  # noqa: E402

RATE = 48000
PEAK_DB = -3.0
SOUNDS = {}


def sound(name: str, loop: bool, **facts):
    """Register a sound; ``facts`` are written to make.json with it (event times the scenes use)."""
    def register(fn):
        SOUNDS[name] = (fn, loop, facts)
        return fn
    return register


def rng_for(name: str) -> np.random.Generator:
    return np.random.default_rng(int.from_bytes(name.encode(), "little") % 2**32)


def t_axis(seconds: float) -> np.ndarray:
    return np.arange(round(seconds * RATE)) / RATE


def periodic_noise(n: int, rng: np.random.Generator, shape) -> np.ndarray:
    """Noise of n samples that loops without a seam, with spectral magnitude shape(f)."""
    f = np.fft.rfftfreq(n, 1 / RATE)
    spec = shape(f) * np.exp(2j * np.pi * rng.random(len(f)))
    spec[0] = 0
    x = np.fft.irfft(spec, n)
    return x / np.abs(x).max()


def band(lo: float, hi: float, order: float = 4.0):
    """Smooth band-pass magnitude for periodic_noise."""
    def shape(f):
        f = np.maximum(f, 1e-3)
        return 1 / np.sqrt(1 + (lo / f) ** (2 * order)) / np.sqrt(1 + (f / hi) ** (2 * order))
    return shape


def slow_wobble(n: int, rng: np.random.Generator, cycles: tuple[int, ...], depth_db: float) -> np.ndarray:
    """Periodic gain curve (linear) from sines with whole numbers of cycles over n samples."""
    ph = np.arange(n) / n
    g = sum(np.sin(2 * np.pi * (c * ph + rng.random())) / len(cycles) for c in cycles)
    return 10 ** (depth_db / 20 * g)


def fade(x: np.ndarray, fade_in_s: float, fade_out_s: float) -> np.ndarray:
    x = x.copy()
    a, b = int(fade_in_s * RATE), int(fade_out_s * RATE)
    if a:
        x[:a] *= (np.sin(0.5 * np.pi * np.arange(a) / a) ** 2)[:, None] if x.ndim == 2 else np.sin(0.5 * np.pi * np.arange(a) / a) ** 2
    if b:
        ramp = np.cos(0.5 * np.pi * np.arange(b) / b) ** 2
        x[-b:] *= ramp[:, None] if x.ndim == 2 else ramp
    return x


def harmonic_tone(freq: np.ndarray, harmonics: list[tuple[int, float]], cutoff_hz: float) -> np.ndarray:
    """Sum of harmonics of a time-varying fundamental (per-sample frequency array), band-limited."""
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    out = np.zeros_like(freq)
    for k, a in harmonics:
        out += a * np.sin(k * phase) * (k * freq < cutoff_hz)
    return out


def resonance(x: np.ndarray, centre_hz: float, q: float) -> np.ndarray:
    """Circular (seam-free) band emphasis around centre_hz, applied in the frequency domain."""
    f = np.fft.rfftfreq(len(x), 1 / RATE)
    h = 1 / np.sqrt(1 + q ** 2 * (f / centre_hz - centre_hz / np.maximum(f, 1e-3)) ** 2)
    return np.fft.irfft(np.fft.rfft(x) * (0.35 + h), len(x))


# --- sounds ---------------------------------------------------------------------------------------

@sound("siren_two_tone", loop=True)
def siren_two_tone(rng):
    """Two-tone horn: 440 and 586 Hz, 0.75 s each, a 3 s loop of whole cycles (440 * 1.5 + 586 * 1.5
    = 1539), glides of 25 ms between the tones, harmonics up to 5 kHz through a horn resonance."""
    n = 3 * RATE
    step = np.repeat([440.0, 586.0, 440.0, 586.0], n // 4)
    k = int(0.025 * RATE)
    kernel = np.ones(k) / k
    freq = np.convolve(np.concatenate([step[-k:], step, step[:k]]), kernel, "same")[k:-k]
    freq *= 1539.0 / (freq.sum() / RATE)  # whole cycles over the loop
    x = harmonic_tone(freq, [(k, 1 / k ** 0.8) for k in range(1, 13)], 5000)
    return resonance(x, 1400, 1.2)


@sound("car_horn", loop=False)
def car_horn(rng):
    """Two horn tones, 420 and 500 Hz, 0.6 s, buzzy (odd and even harmonics), sharp onset."""
    t = t_axis(0.75)
    x = np.zeros_like(t)
    for f0 in (420.0, 500.0):
        x += harmonic_tone(np.full_like(t, f0), [(k, 1 / k) for k in range(1, 16)], 7000)
    x = resonance(x, 2200, 1.5)
    env = np.clip(t / 0.008, 0, 1) * np.clip((0.6 - t) / 0.06 + 1, 0, 1)
    return x * env


@sound("church_bell", loop=False)
def church_bell(rng):
    """One strike of a church bell: hum, prime, tierce, quint, nominal and upper partials over a
    320 Hz prime, the higher partials decaying faster, a short strike noise; 5 s. The longest decay
    (the hum, 60 dB in 4.5 s) is shorter than a real bell's, so that a strike ends within a pass."""
    t = t_axis(5.0)
    prime = 320.0
    partials = [(0.5, 0.8, 4.5), (1.0, 1.0, 4.0), (1.2, 0.7, 3.5), (1.5, 0.35, 2.8), (2.0, 0.9, 2.4),
                (2.51, 0.35, 1.6), (2.66, 0.3, 1.4), (3.01, 0.25, 1.1), (4.07, 0.15, 0.7), (5.2, 0.08, 0.45)]
    x = np.zeros_like(t)
    for ratio, amp, t60 in partials:
        beat = 1 + 0.004 * rng.random()  # a slightly doubled partial beats slowly
        x += amp * np.exp(-6.9 * t / t60) * (np.sin(2 * np.pi * prime * ratio * t + rng.random() * 6)
                                               + 0.3 * np.sin(2 * np.pi * prime * ratio * beat * t))
    strike = rng.standard_normal(len(t)) * np.exp(-t / 0.006)
    x += 0.6 * np.convolve(strike, np.hanning(9) / 4, "same")
    return fade(x, 0.0, 0.5)


@sound("train_horn", loop=False)
def train_horn(rng):
    """Three-chime air horn: 311, 370 and 494 Hz (D#4, F#4, B4) at once, 2 s. Each chime is a reed
    tone (all harmonics up to 6 kHz) that starts 4 % flat and rises to pitch in 80 ms as the air
    pressure builds, with a little breath noise; through the bells' resonance around 1.2 kHz."""
    t = t_axis(2.4)
    x = np.zeros_like(t)
    for i, f0 in enumerate((311.0, 370.0, 494.0)):
        scoop = 1 - 0.04 * np.exp(-t / 0.03)
        wobble = 1 + 0.002 * np.sin(2 * np.pi * (5.3 + i) * t + rng.random() * 6.28)
        x += harmonic_tone(f0 * scoop * wobble, [(k, 1 / k ** 0.75) for k in range(1, 20)], 6000)
    breath = np.fft.irfft(np.fft.rfft(rng.standard_normal(len(t))) * band(600, 4000, 2)(np.fft.rfftfreq(len(t), 1 / RATE)),
                          len(t))
    x = resonance(x / 3 + 0.04 * breath / np.abs(breath).max(), 1200, 1.0)
    env = np.clip(t / 0.06, 0, 1) * np.clip((2.0 - t) / 0.25 + 1, 0, 1)
    return x * env


@sound("tyre_noise", loop=True)
def tyre_noise(rng):
    """Road noise of a rolling vehicle: noise between 400 Hz and 2.5 kHz, slow level changes of
    about 2 dB; a 6 s seamless loop."""
    n = 6 * RATE
    x = periodic_noise(n, rng, band(400, 2500, 2.0))
    return x * slow_wobble(n, rng, (1, 2, 3, 5), 2.0)


@sound("town_bed", loop=True)
def town_bed(rng):
    """Town ambience, stereo: far traffic hum, light wind, and birds placed around the loop; 20 s.
    The two channels are decorrelated noise of the same spectrum."""
    n = 20 * RATE
    out = np.zeros((n, 2))
    for ch in range(2):
        hum = periodic_noise(n, rng, band(50, 350, 2.0)) * slow_wobble(n, rng, (1, 2, 3), 3.0)
        wind = periodic_noise(n, rng, band(200, 1800, 1.5)) * slow_wobble(n, rng, (1, 2, 4, 7), 6.0)
        out[:, ch] = 0.55 * hum + 0.22 * wind
    for _ in range(26):  # bird calls: short chirps, each a few FM syllables, placed around the loop
        start = int(rng.random() * n)
        syll = rng.integers(2, 6)
        f0 = rng.uniform(2800, 5200)
        pan = rng.uniform(-0.8, 0.8)
        gain = 10 ** (rng.uniform(-22, -8) / 20)
        call = []
        for _ in range(syll):
            d = rng.uniform(0.04, 0.11)
            tt = t_axis(d)
            sweep = f0 * (1 + rng.uniform(-0.25, 0.25) * tt / d)
            call.append(np.sin(2 * np.pi * np.cumsum(sweep) / RATE) * np.sin(np.pi * tt / d) ** 2)
            call.append(np.zeros(int(rng.uniform(0.03, 0.08) * RATE)))
        call = gain * np.concatenate(call)
        idx = (start + np.arange(len(call))) % n
        out[idx, 0] += call * np.sqrt(0.5 * (1 - pan))
        out[idx, 1] += call * np.sqrt(0.5 * (1 + pan))
    return out


def place(out: np.ndarray, x: np.ndarray, at_s: float, gain: float = 1.0) -> None:
    """Add x into out at at_s, wrapping around the end (events of a seamless loop)."""
    idx = (int(round(at_s * RATE)) + np.arange(len(x))) % len(out)
    np.add.at(out, idx, gain * x)


def decay(seconds: float, tau_s: float) -> np.ndarray:
    return np.exp(-t_axis(seconds) / tau_s)


def filtered_noise(rng, seconds: float, lo: float, hi: float, order: float = 2.0) -> np.ndarray:
    return periodic_noise(round(seconds * RATE), rng, band(lo, hi, order))


DRUM_BAR_S = 2.0
DRUM_STEP_S = DRUM_BAR_S / 16
DRUM_KICKS = (0, 6, 8, 11)
"""Sixteenth steps of the kick in the bar (120 bpm, one bar of 2 s)."""
DRUM_SNARES = (4, 12)
DRUM_BASS = ((0, 55.0), (3, 55.0), (6, 65.41), (8, 55.0), (10, 82.41), (11, 73.42), (14, 49.0))
"""(step, Hz) of the bass notes: A1, C2, E2, D2, G1."""


@sound("drum_loop", loop=True, kicks_s=[k * DRUM_STEP_S for k in DRUM_KICKS])
def drum_loop(rng):
    """Music from a stage: kick, snare, closed hi-hats on every sixteenth (8 to 12 kHz) and a bass
    line at 120 bpm, one bar of exactly 2 s that repeats without a seam (events wrap around)."""
    n = round(DRUM_BAR_S * RATE)
    out = np.zeros(n)
    t = t_axis(0.35)
    sweep = 48 + 70 * np.exp(-t / 0.03)  # kick: a sine falling from 118 to 48 Hz
    kick = np.sin(2 * np.pi * np.cumsum(sweep) / RATE) * np.exp(-t / 0.12)
    kick[:96] += np.hanning(192)[96:] * 0.4 * rng.standard_normal(96)  # beater click
    for k in DRUM_KICKS:
        place(out, kick, k * DRUM_STEP_S, 0.8)
    for k in DRUM_SNARES:
        t = t_axis(0.25)
        body = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.05)
        rattle = filtered_noise(rng, 0.25, 1500, 7000) * np.exp(-t / 0.06)
        place(out, 0.5 * body + 0.6 * rattle, k * DRUM_STEP_S)
    for k in range(16):  # closed hi-hats, the off-beats louder
        hat = filtered_noise(rng, 0.06, 8000, 12000, 4.0) * decay(0.06, 0.012)
        place(out, hat, k * DRUM_STEP_S, 0.35 if k % 2 else 0.2)
    for i, (k, f0) in enumerate(DRUM_BASS):
        end = DRUM_BASS[i + 1][0] if i + 1 < len(DRUM_BASS) else 16
        t = t_axis((end - k) * DRUM_STEP_S * 0.9)
        note = harmonic_tone(np.full_like(t, f0), [(1, 1.0), (2, 0.5), (3, 0.25), (4, 0.12)], 400)
        place(out, 0.45 * note * np.clip(t / 0.005, 0, 1) * np.exp(-t / 0.4) * np.clip((t[-1] - t) / 0.01, 0, 1),
              k * DRUM_STEP_S)
    for k in (2, 6, 10, 14):  # chord stabs on the off-beats: A minor, 220 to 880 Hz
        t = t_axis(0.18)
        stab = sum(harmonic_tone(np.full_like(t, f), [(1, 1.0), (2, 0.4), (3, 0.2)], 4000) for f in (220.0, 261.63, 329.63))
        place(out, 0.12 * stab * np.clip(t / 0.004, 0, 1) * np.exp(-t / 0.07), k * DRUM_STEP_S)
    return out


@sound("hammer_hit", loop=False)
def hammer_hit(rng):
    """Hammer on wood: a 2 ms click and a 900 Hz knock with a lower wood resonance, 120 ms."""
    t = t_axis(0.12)
    click = rng.standard_normal(len(t)) * np.clip(1 - t / 0.002, 0, 1)
    knock = np.sin(2 * np.pi * 900 * t) * np.exp(-t / 0.018) + 0.6 * np.sin(2 * np.pi * 340 * t) * np.exp(-t / 0.03)
    return fade(0.8 * click + knock, 0.0, 0.02)


@sound("thunder", loop=False)
def thunder(rng):
    """Thunder: a crack, then 4 s of rolling rumble below 300 Hz with a few swells; 4.5 s."""
    t = t_axis(4.5)
    crack = filtered_noise(rng, 4.5, 200, 6000, 1.0) * np.exp(-t / 0.06)
    rumble = filtered_noise(rng, 4.5, 25, 300, 2.0)
    swells = sum(a * np.exp(-0.5 * ((t - c) / w) ** 2) for a, c, w in ((1.0, 0.5, 0.35), (0.7, 1.4, 0.5),
                                                                       (0.8, 2.3, 0.6), (0.4, 3.3, 0.7)))
    roll = filtered_noise(rng, 4.5, 2, 12, 2.0)  # slow random flutter of the level
    out = 0.7 * crack + rumble * swells * (1 + 0.5 * roll / np.abs(roll).max())
    return fade(out, 0.0, 0.8)



@sound("prop_plane", loop=True)
def prop_plane(rng):
    """Light propeller plane at cruise power: a two-blade propeller on a four-cylinder engine at
    2700 rpm, so blade pass and firing are both 90 Hz; a 4 s loop of 360 whole cycles. The propeller
    is a buzzy harmonic series up to 4 kHz whose level varies a little from blade to blade; the
    exhaust is a noise burst on every firing, the four cylinders slightly unequal; a 45 Hz crank
    rumble and air hiss underneath."""
    n, f0 = 4 * RATE, 90.0
    period = RATE / f0
    jitter = np.repeat(1 + 0.08 * rng.standard_normal(round(4 * f0)), int(np.ceil(period)))[:n]
    jitter = np.convolve(np.concatenate([jitter[-64:], jitter, jitter[:64]]), np.hanning(64) / 32, "same")[64:-64]
    prop = harmonic_tone(np.full(n, f0), [(k, 1 / k ** 0.85) for k in range(1, 45)], 4000) * jitter
    exhaust = np.zeros(n)
    bursts = periodic_noise(RATE, rng, band(120, 2500, 1.5))
    cylinders = (1.0, 0.85, 0.95, 0.8)
    env = np.exp(-t_axis(0.03) / 0.004)
    for i in range(round(4 * f0)):
        a = int(rng.integers(0, RATE - len(env)))
        gain = cylinders[i % 4] * (1 + 0.12 * rng.standard_normal())
        place(exhaust, bursts[a:a + len(env)] * env, (i * period + rng.normal(0, 4)) / RATE, gain)
    rumble = np.sin(2 * np.pi * 45.0 * t_axis(4.0))
    hiss = periodic_noise(n, rng, band(1500, 8000, 1.5)) * slow_wobble(n, rng, (1, 2, 3), 2.0)
    return prop / np.abs(prop).max() + 0.8 * exhaust / np.abs(exhaust).max() + 0.25 * rumble + 0.12 * hiss

# --- probes (sections/README.md, S4): known signals that the checks measure ------------------------

@sound("sine_1k", loop=True)
def sine_1k(rng):
    """1 kHz sine, 4 s, whole cycles."""
    return np.sin(2 * np.pi * 1000.0 * t_axis(4.0))


@sound("noise_pink", loop=True)
def noise_pink(rng):
    """Pink noise from 20 Hz, 4 s, seamless."""
    return periodic_noise(4 * RATE, rng, lambda f: np.where(f > 20, 1 / np.sqrt(np.maximum(f, 1)), 0.0))


@sound("noise_burst", loop=False)
def noise_burst(rng):
    """White noise, 0.1 s with 1 ms raised-cosine edges, then 0.4 s of silence."""
    x = np.zeros(RATE // 2)
    x[:RATE // 10] = fade(rng.standard_normal(RATE // 10), 0.001, 0.001)
    return x


@sound("click", loop=False)
def click(rng):
    """One sample at full scale (before the -3 dB peak), then 1 s of silence."""
    x = np.zeros(RATE)
    x[0] = 1.0
    return x


# --- driver ---------------------------------------------------------------------------------------

def write(out: Path, name: str, x: np.ndarray) -> Path:
    x = x / np.abs(x).max() * 10 ** (PEAK_DB / 20)
    path = out / f"{name}.wav"
    sf.write(path, x, RATE, subtype="PCM_24")
    return path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="out/showcase/sounds")
    p.add_argument("names", nargs="*", help="sounds to make (default: all)")
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    unknown = set(a.names) - set(SOUNDS)
    if unknown:
        sys.exit(f"unknown sounds: {', '.join(sorted(unknown))}")
    summary_path = out / "make.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    summary = {k: v for k, v in summary.items() if k in SOUNDS}  # drop sounds no longer made here
    for name, (fn, loop, facts) in SOUNDS.items():
        if a.names and name not in a.names:
            continue
        path = write(out, name, fn(rng_for(name)))
        x, rate = sf.read(path, always_2d=True)
        summary[name] = {"loop": loop, **facts, **measure.sound_facts(x, rate, loop)}
        print(f"{name:18s} {measure.describe(summary[name])}")
    summary_path.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
