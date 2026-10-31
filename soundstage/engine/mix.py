"""Master processing and file output.

- ``normalize_gain``: gain that brings the master to a loudness target (ITU-R BS.1770, pyloudnorm).
- ``true_peak``: per-sample true peak (ITU-R BS.1770-4 Annex 2): 4x oversampled through a
  Kaiser low-pass flat to 20 kHz at 48 kHz (32 taps per phase).
- ``true_peak_limiter``: offline look-ahead limiter on the true peak, checked 8x oversampled, so
  that 4x meters (the report, ffmpeg, Resolve) read at most the ceiling: the gain needed per sample
  is spread backwards over the look-ahead (sliding minimum, then a box average of half its width,
  so the gain is already down when the peak arrives) and recovers with an exponential release; a
  check pass tightens the gain if the result still overshoots. It returns a gain curve, applied to
  the master and to every stem, so stems keep summing to the master.
- ``write_wav``: 32-bit float by default, or 24-bit PCM with TPDF dither (seeded, deterministic).
  Sample 0 = the first frame of the rendered range.

Off by default (final mixing happens in Resolve, FR-64). Model and choices:
research/models/mixing-and-loudness.md; spec: docs/spec/signal-model.md#mixing-and-output.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

import numba
import numpy as np
import pyloudnorm
import soundfile as sf
from scipy.ndimage import minimum_filter1d, uniform_filter1d
from scipy.signal import firwin, resample_poly

OVERSAMPLE = 4  # true-peak meter (BS.1770-4)
LIMITER_OVERSAMPLE = 8  # the limiter's own check: 4x meters may read up to 0.5 dB low near 20 kHz
SFC_SET_ADD_PEAK_CHUNK = 0x1050  # libsndfile command (sndfile.h)


def normalize_gain(audio: np.ndarray, rate: int, target_lufs: float) -> float:
    """Linear gain that brings the integrated loudness to ``target_lufs`` (1.0 for silence)."""
    lufs = pyloudnorm.Meter(rate).integrated_loudness(audio)
    return 1.0 if not np.isfinite(lufs) else float(10.0 ** ((target_lufs - lufs) / 20.0))


@functools.cache
def _interpolator(factor: int) -> np.ndarray:
    """Oversampling low-pass at the original Nyquist: 32 taps per phase, Kaiser beta 8 (flat within
    0.01 dB to 20 kHz at 48 kHz, images above 28 kHz down 69 dB)."""
    return firwin(32 * factor + 1, 1.0 / factor, window=("kaiser", 8.0))


def true_peak(audio: np.ndarray, oversample: int = OVERSAMPLE) -> np.ndarray:
    """Per-sample true peak (max over channels and the oversampled values within each sample)."""
    x = audio if audio.ndim == 2 else audio[:, None]
    up = np.abs(resample_poly(x, oversample, 1, axis=0, window=_interpolator(oversample)))
    n = len(x)
    return up[: n * oversample].reshape(n, oversample, -1).max(axis=(1, 2))


@numba.njit(cache=True, nogil=True)
def _release(g, alpha):
    out = np.empty_like(g)
    level = 1.0
    for i in range(g.shape[0]):
        level = g[i] if g[i] < level else level + (g[i] - level) * (1.0 - alpha)
        out[i] = level
    return out


def true_peak_limiter(audio: np.ndarray, rate: int, ceiling_dbtp: float, lookahead_ms: float = 5.0,
                      release_ms: float = 80.0) -> np.ndarray:
    """Gain curve (n,) that keeps the true peak of ``audio * gain`` at or below the ceiling."""
    ceiling = 10.0 ** (ceiling_dbtp / 20.0)
    look = max(1, int(lookahead_ms * 1e-3 * rate))
    alpha = float(np.exp(-1.0 / (release_ms * 1e-3 * rate)))
    gain = np.ones(len(audio))
    for _ in range(4):
        tp = true_peak(audio * gain[:, None], LIMITER_OVERSAMPLE)
        if tp.max() <= ceiling * 1.0001:
            break
        need = np.minimum(1.0, ceiling / np.maximum(tp, 1e-12))
        g = minimum_filter1d(need, size=2 * look + 1, mode="nearest")
        g = uniform_filter1d(g, size=look + 1, mode="nearest")
        gain = gain * _release(np.minimum(g, need), alpha)
    return gain


def finish(audio: np.ndarray, stems: dict[str, np.ndarray], rate: int, *, normalize: float | None = None,
           limit: float | None = None) -> dict:
    """Normalize and limit the master in place, applying the same gains to the stems."""
    info: dict = {}
    if normalize is not None:
        g = normalize_gain(audio, rate, normalize)
        audio *= g
        for s in stems.values():
            s *= g
        info["normalize_gain_db"] = round(20 * np.log10(g), 2)
    if limit is not None:
        curve = true_peak_limiter(audio, rate, limit)
        audio *= curve[:, None]
        for s in stems.values():
            s *= curve[:, None].astype(s.dtype)
        info["limiter_max_reduction_db"] = round(abs(float(20 * np.log10(curve.min()))), 2)
        info["limiter_active_s"] = round(float(np.sum(curve < 0.999) / rate), 3)
    return info


def stem_path(output: Path, group: str) -> Path:
    """``<mix>_stem_<group>.wav`` next to the mix; characters other than letters, digits, ``-``, ``_``
    and ``.`` in the group name become ``_``."""
    name = re.sub(r"[^\w.-]", "_", group)
    return output.with_name(f"{output.stem}_stem_{name}{output.suffix}")


def write_wav(path: str | Path, audio: np.ndarray, rate: int, *, pcm24: bool = False) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if pcm24:
        lsb = 2.0 ** -23
        rng = np.random.default_rng(0)
        dither = (rng.random(audio.shape) - rng.random(audio.shape)) * lsb
        data = np.clip(audio + dither, -1.0, 1.0 - lsb)
        sf.write(path, data, rate, subtype="PCM_24")
    else:
        with sf.SoundFile(path, "w", rate, audio.shape[1] if audio.ndim == 2 else 1, subtype="FLOAT") as f:
            # no PEAK chunk: libsndfile stamps it with the time of writing, so files would differ (NFR-2)
            try:
                sf._snd.sf_command(f._file, SFC_SET_ADD_PEAK_CHUNK, sf._ffi.NULL, 0)
            except AttributeError:  # another soundfile build: the file is still correct, only its bytes vary
                pass
            f.write(audio.astype(np.float32))
    return path
