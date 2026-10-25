"""Reverb: environment impulse responses and the send bus.

- Presets: the EFX reverb presets (I3DL2/EAX parameter sets, ``data/efx_presets.json``), from which a
  stereo impulse response is synthesized: sparse early reflections, then a late tail of
  exponentially decaying noise whose decay time follows the preset's low/mid/high decay times over
  frequency (Moorer: decaying noise is a natural late reverberation; high frequencies decay
  faster), in complementary 1/3-octave bands. Low diffusion gives a sparse ("velvet") tail. Left
  and right use independent noise (decorrelated). Each section's energy is set by the preset's gains; ``gain_hf``/``gain_lf`` shelve the whole
  response. Seeded from the preset name: renders are reproducible (NFR-2).
- Files: a WAV/FLAC impulse response, resampled to the output rate, used as recorded.
- ``ReverbBus``: the sum of all sources' sends is convolved once per chunk (FFT overlap-add); the
  tail carries over to the next chunk, so chunked output equals one long convolution.

Model and choices: research/models/reverb.md; spec: docs/spec/signal-model.md#reverb.
"""

from __future__ import annotations

import difflib
import functools
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.fft import next_fast_len
from scipy.signal import oaconvolve, sosfilt

DATA = Path(__file__).resolve().parent / "data" / "efx_presets.json"
MAX_SECONDS = 15.0
SPEED_OF_SOUND = 343.0


@functools.lru_cache(maxsize=1)
def presets() -> dict[str, dict]:
    return json.loads(DATA.read_text())["presets"]


def preset(name: str) -> dict:
    table = presets()
    key = name.lower()
    if key not in table:
        close = difflib.get_close_matches(key, table, n=4)
        raise ValueError(f"unknown reverb preset {name!r}" + (f"; did you mean {', '.join(close)}?" if close else ""))
    return table[key]


def decay_times(p: dict) -> tuple[float, float, float]:
    """Low, mid and high band decay times (s) of a preset, with EFX's HF limit from air absorption."""
    t_mid = p["decay_time"]
    t_lf = t_mid * p["decay_lf_ratio"]
    t_hf = t_mid * p["decay_hf_ratio"]
    if p.get("decay_hf_limit") and p["air_absorption_gain_hf"] < 1.0:
        db_per_m = -20.0 * math.log10(p["air_absorption_gain_hf"])
        t_hf = min(t_hf, 60.0 / (db_per_m * SPEED_OF_SOUND))
    return t_lf, t_mid, t_hf


def _shelf_sos(freq: float, gain: float, rate: int, high: bool) -> np.ndarray:
    """First-order shelf (bilinear) with ``gain`` above (high) or below (low) ``freq``."""
    k = math.tan(math.pi * min(freq, 0.45 * rate) / rate)
    if high:  # H(s) = (g s + w) / (s + w)
        b0, b1 = gain + k, k - gain
    else:  # H(s) = (s + g w) / (s + w)
        b0, b1 = 1.0 + gain * k, gain * k - 1.0
    a0, a1 = 1.0 + k, k - 1.0
    return np.array([[b0 / a0, b1 / a0, 0.0, 1.0, a1 / a0, 0.0]])


BANDS_PER_OCTAVE = 3
LOWEST_BAND_HZ = 20.0


def decay_curve(f: np.ndarray, p: dict) -> np.ndarray:
    """Decay time T60(f): the preset's low, mid and high decay times, blended in decay *rate* with
    steep (4th-order) transitions at ``lf_reference`` and ``hf_reference``."""
    t_lf, t_mid, t_hf = decay_times(p)
    fl = np.maximum(f, 1.0)
    low = 1.0 / (1.0 + (fl / p["lf_reference"]) ** 4)
    high = (fl / p["hf_reference"]) ** 4 / (1.0 + (fl / p["hf_reference"]) ** 4)
    rate = 1.0 / t_mid + (1.0 / t_lf - 1.0 / t_mid) * low + (1.0 / t_hf - 1.0 / t_mid) * high
    return 1.0 / rate


def _decaying(noise: np.ndarray, p: dict, rate: int) -> np.ndarray:
    """Apply the frequency-dependent exponential decay to ``noise``: complementary 1/3-octave bands
    (raised-cosine crossfades between neighbouring centres on a log-frequency axis, summing to 1,
    applied in one FFT over the whole signal), each times the decay of T60 at its centre."""
    n = len(noise)
    spec = np.fft.rfft(noise)
    f = np.fft.rfftfreq(n, 1.0 / rate)
    x = np.log2(np.maximum(f, LOWEST_BAND_HZ / 2) / LOWEST_BAND_HZ) * BANDS_PER_OCTAVE  # band-index axis
    count = int(x[-1]) + 1
    t60 = decay_curve(LOWEST_BAND_HZ * 2.0 ** (np.arange(count) / BANDS_PER_OCTAVE), p)
    t = np.arange(n) / rate
    out = np.zeros(n)
    band = np.zeros_like(spec)
    for k in range(count):
        a = 0 if k == 0 else int(np.searchsorted(x, k - 1, side="right"))
        b = len(x) if k == count - 1 else int(np.searchsorted(x, k + 1))
        band[:] = 0.0
        w = 0.5 + 0.5 * np.cos(np.pi * np.clip(x[a:b] - k, -1.0, 1.0))
        if k == 0:
            w[x[a:b] < 0] = 1.0
        if k == count - 1:
            w[x[a:b] > k] = 1.0
        band[a:b] = spec[a:b] * w
        out += np.fft.irfft(band, n) * np.exp(-3.0 * math.log(10.0) * t / t60[k])
    return out


def synthesize(p: dict, rate: int, seed: int) -> np.ndarray:
    """Stereo impulse response (n, 2) for EFX preset parameters ``p``."""
    rng = np.random.default_rng(seed)
    t_lf, t_mid, t_hf = decay_times(p)
    late_start = p["reflections_delay"] + p["late_reverb_delay"]
    n = int(min(late_start + 1.1 * max(t_lf, t_mid, t_hf), MAX_SECONDS) * rate)
    ir = np.zeros((n, 2))

    # early reflections: sparse taps between the first reflection and the start of the late tail
    e0 = int(p["reflections_delay"] * rate)
    e1 = max(int(late_start * rate), e0 + int(0.01 * rate))
    taps = int(round(8 + 16 * p["density"]))
    for ch in range(2):
        pos = np.sort(rng.integers(e0, min(e1, n - 1), taps))
        amp = rng.choice([-1.0, 1.0], taps) * np.exp(-3.0 * (pos - e0) / max(e1 - e0, 1))
        early = np.zeros(n)
        np.add.at(early, pos, amp)
        early *= p["gain"] * p["reflections_gain"] / math.sqrt(np.sum(early ** 2))
        ir[:, ch] += early

    # late tail: decaying noise per band; sparse (velvet) when diffusion is low
    l0 = int(late_start * rate)
    m = n - l0
    density = 300.0 + 3700.0 * p["diffusion"] ** 2  # pulses per second
    ramp = int(0.005 * rate)
    def excitation(length: int) -> np.ndarray:
        if p["diffusion"] >= 0.99:
            return rng.standard_normal(length)
        period = rate / density  # velvet noise: one +-1 pulse per period
        noise = np.zeros(length)
        idx = (np.arange(0, length, period) + rng.uniform(0, period, int(np.ceil(length / period)))).astype(int)
        idx = idx[idx < length]
        noise[idx] = rng.choice([-1.0, 1.0], len(idx))
        return noise

    for ch in range(2):
        late = _decaying(excitation(next_fast_len(m, real=True)), p, rate)[:m]
        late[:ramp] *= np.linspace(0.0, 1.0, ramp)  # no click at the onset
        late *= p["gain"] * p["late_reverb_gain"] / math.sqrt(np.sum(late ** 2))
        ir[l0:, ch] += late

    if p["gain_hf"] != 1.0:
        ir = sosfilt(_shelf_sos(p["hf_reference"], p["gain_hf"], rate, high=True), ir, axis=0)
    if p["gain_lf"] != 1.0:
        ir = sosfilt(_shelf_sos(p["lf_reference"], p["gain_lf"], rate, high=False), ir, axis=0)
    return ir


def seed_for(name: str) -> int:
    return int.from_bytes(hashlib.sha256(f"reverb:{name}".encode()).digest()[:8], "little")


@dataclass
class Environment:
    name: str  # preset name or file path
    ir: np.ndarray  # (n, 2) at the output rate
    room_rolloff: float  # rolloff factor of the send with distance (EFX room rolloff)


@functools.lru_cache(maxsize=4)
def _synthesized(name: str, rate: int) -> np.ndarray:
    return synthesize(preset(name), rate, seed_for(name))


def environment(spec: str, rate: int, room_rolloff: float | None = None) -> Environment:
    """A preset name (``hangar``, ``city``, ``spacestation_hall`` ...) or an impulse-response file."""
    path = Path(spec).expanduser()
    if path.suffix.lower() in (".wav", ".flac", ".ogg", ".aif", ".aiff") or path.exists():
        import soundfile as sf
        import soxr

        data, file_rate = sf.read(str(path), dtype="float64", always_2d=True)
        data = data[:, :2] if data.shape[1] >= 2 else np.repeat(data, 2, axis=1)
        if file_rate != rate:
            data = soxr.resample(data, file_rate, rate, quality="VHQ")
        return Environment(str(path), np.ascontiguousarray(data), 0.0 if room_rolloff is None else room_rolloff)
    name = spec.lower()
    p = preset(name)
    return Environment(name, _synthesized(name, rate), p["room_rolloff_factor"] if room_rolloff is None else room_rolloff)


class ReverbBus:
    """Convolves the summed mono send with the stereo IR, chunk by chunk (overlap-add with a tail)."""

    def __init__(self, env: Environment):
        self.ir = env.ir
        self.tail = np.zeros((len(env.ir) - 1, 2))

    def process(self, send: np.ndarray) -> np.ndarray:
        n = len(send)
        if not np.any(send) and not np.any(self.tail):
            return np.zeros((n, 2))
        full = oaconvolve(send[:, None], self.ir, axes=0)  # (n + len(ir) - 1, 2)
        full[: len(self.tail)] += self.tail
        out = full[:n].copy()
        rest = full[n:]
        self.tail = np.zeros_like(self.tail)
        self.tail[: len(rest)] = rest
        return out


def rt60(ir: np.ndarray, rate: int, band: tuple[float, float] | None = None) -> float:
    """Reverberation time from Schroeder backward integration (T30 fit, -5 to -35 dB), mono sum."""
    x = ir.sum(axis=1) if ir.ndim == 2 else ir
    if band is not None:
        from scipy.signal import butter, sosfiltfilt

        x = sosfiltfilt(butter(4, band, btype="bandpass", fs=rate, output="sos"), x)
    edc = np.cumsum((x ** 2)[::-1])[::-1]
    edc_db = 10 * np.log10(edc / edc[0] + 1e-30)
    i5, i35 = int(np.argmax(edc_db <= -5)), int(np.argmax(edc_db <= -35))
    t = np.arange(len(x)) / rate
    slope = np.polyfit(t[i5:i35], edc_db[i5:i35], 1)[0]
    return -60.0 / slope


def expected_rt60(p: dict, rate: int, band: tuple[float, float]) -> float:
    """The T30 that ``rt60`` should measure in ``band`` on an impulse response of preset ``p``: the
    energy decay of white noise with decay time ``decay_curve(f)``, weighted by the band filter."""
    from scipy.signal import butter, sosfreqz

    f = np.linspace(max(1.0, band[0] / 4), min(band[1] * 4, 0.5 * rate - 1), 800)
    _, h = sosfreqz(butter(4, band, btype="bandpass", fs=rate, output="sos"), worN=f, fs=rate)
    weight = np.abs(h) ** 4 * np.gradient(f)  # filtered forward and backward: |H|^4 in power
    t60 = decay_curve(f, p)
    k = 6.0 * math.log(10.0) / t60  # energy decay rate
    t = np.linspace(0.0, 3.0 * t60.max(), 600)  # within 0.3 % of a 5x finer grid
    edc = (weight * np.exp(-np.outer(t, k)) / k).sum(axis=1)
    edc_db = 10 * np.log10(edc / edc[0])
    i5, i35 = int(np.argmax(edc_db <= -5)), int(np.argmax(edc_db <= -35))
    return -60.0 / np.polyfit(t[i5:i35], edc_db[i5:i35], 1)[0]
