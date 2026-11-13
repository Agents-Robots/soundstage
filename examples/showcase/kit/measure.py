"""Measurement helpers for the sounds and the checks (repo venv: numpy, scipy, pyloudnorm).

The checks assert the known answers of a section's README on rendered probes; these functions do
the measuring: levels, band levels, frequency over time, onsets, loudness.
"""

from __future__ import annotations

import numpy as np
from scipy import signal

from soundstage.engine import report


def db(x: float) -> float:
    return float(20 * np.log10(max(float(x), 1e-12)))


def rms_db(x: np.ndarray) -> float:
    return float(10 * np.log10(max(float(np.mean(np.square(x))), 1e-24)))


def mono(x: np.ndarray) -> np.ndarray:
    return x.mean(axis=1) if x.ndim == 2 else x


def short_term_db(x: np.ndarray, rate: int, window_s: float = 0.4, hop_s: float = 0.1) -> np.ndarray:
    m = mono(x)
    w, h = int(window_s * rate), int(hop_s * rate)
    return np.array([rms_db(m[i:i + w]) for i in range(0, max(len(m) - w, 1), h)])


def band_db(x: np.ndarray, rate: int, lo: float, hi: float) -> float:
    """Level of one channel (or the mono sum) in a band, by FFT."""
    m = mono(x)
    spec = np.fft.rfft(m * np.hanning(len(m)))
    f = np.fft.rfftfreq(len(m), 1 / rate)
    sel = (f >= lo) & (f < hi)
    return float(10 * np.log10(max(np.sum(np.abs(spec[sel]) ** 2), 1e-30)))


def frequency(x: np.ndarray, rate: int, near_hz: float | None = None) -> float:
    """Frequency of the strongest spectral peak, refined by parabolic interpolation (Hz)."""
    m = mono(x)
    n = 1 << int(np.ceil(np.log2(len(m) * 8)))
    spec = np.abs(np.fft.rfft(m * np.hanning(len(m)), n))
    f = np.fft.rfftfreq(n, 1 / rate)
    if near_hz:
        spec = np.where(np.abs(f - near_hz) < 0.5 * near_hz, spec, 0)
    i = int(np.argmax(spec))
    a, b, c = np.log(spec[i - 1: i + 2] + 1e-30)
    return float(f[i] + 0.5 * (a - c) / (a - 2 * b + c) * (f[1] - f[0]))


def frequency_track(x: np.ndarray, rate: int, window_s: float = 0.1, hop_s: float = 0.02,
                    near_hz: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(times of window centres, frequency) of the strongest peak over time."""
    m = mono(x)
    w, h = int(window_s * rate), int(hop_s * rate)
    starts = np.arange(0, len(m) - w, h)
    freqs = np.array([frequency(m[s:s + w], rate, near_hz) if np.any(m[s:s + w]) else np.nan for s in starts])
    return (starts + w / 2) / rate, freqs


def onsets(x: np.ndarray, rate: int, threshold_db: float = -50.0, hold_s: float = 0.05) -> list[float]:
    """Times (s) where the absolute signal first exceeds threshold_db after hold_s of silence."""
    m = np.abs(mono(x))
    above = np.flatnonzero(m > 10 ** (threshold_db / 20))
    out, last = [], -1e9
    for i in above:
        if (i - last) / rate > hold_s:
            out.append(i / rate)
        last = i
    return out


def channel_balance_db(x: np.ndarray) -> float:
    """Left minus right level (dB)."""
    return rms_db(x[:, 0]) - rms_db(x[:, 1])


def loop_seam_db(x: np.ndarray, rate: int) -> float:
    """Level of the step at the loop seam relative to the signal's RMS: the end joined to the start
    should look like any other sample-to-sample step."""
    m = mono(x)
    steps = np.abs(np.diff(m))
    seam = abs(m[0] - m[-1])
    return db(seam / (np.percentile(steps, 99) + 1e-12))


def pitch_drift(x: np.ndarray, rate: int) -> float:
    """Relative spread (p90/p10 - 1) of the spectral centroid over 0.4 s windows: a coarse measure of
    pitch and timbre drift in a loop."""
    m = mono(x)
    w = int(0.4 * rate)
    cents = []
    for i in range(0, len(m) - w, w // 2):
        f, p = signal.periodogram(m[i:i + w], rate)
        sel = (f > 40) & (f < 4000)
        cents.append(np.sum(f[sel] * p[sel]) / max(np.sum(p[sel]), 1e-30))
    cents = np.array(cents)
    return float(np.percentile(cents, 90) / np.percentile(cents, 10) - 1) if len(cents) > 2 else 0.0


def sound_facts(x: np.ndarray, rate: int, loop: bool) -> dict:
    """What sounds/README.md asks to be measured for every sound (A4 to A6)."""
    out = {"seconds": round(len(x) / rate, 3), "channels": int(x.shape[1]), "rate": rate,
           "peak_dbfs": round(db(np.abs(x).max()), 2), **report.metrics(x if x.ndim == 2 else x[:, None], rate)}
    if loop:
        st = short_term_db(x, rate)
        out["level_spread_db"] = round(float(np.percentile(st, 95) - np.percentile(st, 5)), 2)
        out["seam_step_db"] = round(loop_seam_db(x, rate), 1)
        out["centroid_drift"] = round(pitch_drift(x, rate), 3)
    else:
        first = onsets(x, rate, threshold_db=out["peak_dbfs"] - 30)
        out["onset_ms"] = round(1000 * first[0], 1) if first else None
        out["end_dbfs"] = round(db(np.abs(mono(x)[-int(0.01 * rate):]).max()), 1)
    return out


def describe(f: dict) -> str:
    s = f"{f['seconds']:6.2f} s  ch {f['channels']}  peak {f['peak_dbfs']:6.1f} dBFS  {f.get('lufs_integrated')} LUFS"
    if "level_spread_db" in f:
        s += f"  spread {f['level_spread_db']} dB  seam {f['seam_step_db']} dB  drift {f['centroid_drift']}"
    else:
        s += f"  onset {f['onset_ms']} ms  end {f['end_dbfs']} dBFS"
    return s
