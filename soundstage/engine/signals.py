"""Samples and dry timelines.

- Decode samples with soundfile (WAV, FLAC, OGG), cache per path; downmix spatial sources to mono,
  keep beds stereo.
- Resample to the output rate with soxr; apply ``pitch`` as an extra ratio.
- Build each source's dry signal over an output sample window: loops tiled with a correlation-adaptive
  seam crossfade and a seeded start phase, one-shots placed at their trigger sample,
  raised-cosine fades.

Spatial sources are built at the emission rate (2x the output rate for the ``optimal2x``
interpolator) over emission time; beds at the output rate over reception time.
Spec: docs/spec/signal-model.md#dry-timeline.
"""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache

import numpy as np
import soundfile as sf
import soxr


@lru_cache(maxsize=64)
def _decode(path: str, mtime: float) -> tuple[np.ndarray, int]:
    data, rate = sf.read(path, dtype="float64", always_2d=True)
    return data, rate


def load_sample(path: str, rate: int, *, pitch: float = 1.0, stereo: bool = False) -> np.ndarray:
    """Decoded sample at ``rate`` (pitch applied): shape (n,) mono, or (n, 2) if ``stereo``.

    Mono output averages all channels. Stereo output keeps the first two channels; a mono file is
    copied to both channels at -3.01 dB.
    """
    data, src_rate = _decode(path, os.path.getmtime(path))
    if stereo:
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1) / np.sqrt(2.0)
        else:
            data = data[:, :2]
    else:
        data = data.mean(axis=1)
    target = rate / pitch
    if abs(target - src_rate) > 1e-9:
        data = soxr.resample(data, src_rate, target, quality="VHQ")
    return np.ascontiguousarray(data, dtype=np.float64)


def seed_for(source_id: str) -> int:
    """Stable random seed from a source id (NFR-2)."""
    return int.from_bytes(hashlib.sha256(source_id.encode()).digest()[:8], "little")


def raised_cosine(n: int) -> np.ndarray:
    """Ramp from 0 to 1 over n samples (first sample 0, last sample 1)."""
    if n <= 1:
        return np.ones(max(n, 0))
    return 0.5 - 0.5 * np.cos(np.pi * np.arange(n) / (n - 1))


def loop_cycle(x: np.ndarray, crossfade: int) -> np.ndarray:
    """One period of a seamless loop: the tail is crossfaded into the head.

    The crossfade law adapts to the correlation rho of the overlapping head and tail: gains
    a, b with a^2 + b^2 + 2 rho a b = 1, i.e. equal power for uncorrelated material (rho = 0) and
    equal gain for identical material (rho = 1), so the level stays constant across the seam.
    """
    n = len(x)
    c = min(crossfade, n // 2)
    if c <= 0:
        return x.copy()
    cycle = x[: n - c].copy()
    head, tail = x[:c], x[n - c:]
    energy = np.sqrt(np.sum(head * head) * np.sum(tail * tail))
    rho = float(np.clip(np.sum(head * tail) / energy, 0.0, 1.0)) if energy > 0 else 0.0
    u = (np.arange(c) + 0.5) / c
    fade_in, fade_out = np.sin(0.5 * np.pi * u), np.cos(0.5 * np.pi * u)
    norm = 1.0 / np.sqrt(fade_in ** 2 + fade_out ** 2 + 2.0 * rho * fade_in * fade_out)
    fade_in, fade_out = fade_in * norm, fade_out * norm
    if x.ndim == 2:
        fade_in, fade_out = fade_in[:, None], fade_out[:, None]
    cycle[:c] = x[:c] * fade_in + x[n - c:] * fade_out
    return cycle


def _envelope(n0: int, n1: int, start: int | None, fade_in: int, end: int | None, fade_out: int) -> np.ndarray:
    """Gain envelope over [n0, n1): 0 before start, ramp up, 1, ramp down from end, 0 after."""
    idx = np.arange(n0, n1)
    env = np.ones(n1 - n0)
    if start is not None:
        env[idx < start] = 0.0
        if fade_in > 0:
            k = (idx >= start) & (idx < start + fade_in)
            env[k] = raised_cosine(fade_in + 1)[1:][idx[k] - start]
    if end is not None:
        env[idx >= end + fade_out] = 0.0
        if fade_out > 0:
            k = (idx >= end) & (idx < end + fade_out)
            env[k] *= raised_cosine(fade_out + 1)[::-1][:-1][idx[k] - end]
    return env


class DryGenerator:
    """Dry signal of one source, produced window by window (loop cycle and phase computed once).

    Sample indices are at ``rate`` (the emission rate for spatial sources, the output rate for beds)
    with index 0 at the first frame; ``start``/``end`` are the indices of the tag's
    ``frame``/``end_frame`` (None if unset); for one-shots ``start`` may be a list of triggers.
    """

    def __init__(self, sample: np.ndarray, params: dict, rate: int, start, end: int | None, source_id: str,
                 prefilter: np.ndarray | None = None):
        """``prefilter``: a symmetric FIR applied once to the sample (one-shots, which then start
        ``len // 2`` samples early) or circularly to the loop cycle (exactly periodic)."""
        self.sample, self.params, self.rate = sample, params, rate
        self.start, self.end = start, end
        self.lead = 0
        self.fade_in = int(round(params["fade_in"] * rate))
        self.fade_out = int(round(params["fade_out"] * rate))
        self.once = params["mode"] == "once"
        if self.once and prefilter is not None:
            self.sample = np.convolve(sample, prefilter)  # full: starts len // 2 before the trigger
            self.lead = len(prefilter) // 2
        if not self.once:
            self.cycle = loop_cycle(sample, int(round(params["loop_crossfade"] * rate)))
            if prefilter is not None:
                m = len(prefilter) // 2
                wrapped = np.concatenate([self.cycle[-m:], self.cycle, self.cycle[:m]]) if m else self.cycle
                self.cycle = np.convolve(wrapped, prefilter, mode="valid")
            period = len(self.cycle)
            if params["loop_phase"] == "random":
                self.phase = int(np.random.default_rng(seed_for(source_id)).integers(0, period))
            else:
                self.phase = int(round(params["loop_phase"] * rate)) % period

    def window(self, n0: int, n1: int) -> np.ndarray:
        """Samples [n0, n1)."""
        sample = self.sample
        if self.once:
            out = np.zeros((n1 - n0,) + sample.shape[1:])
            for start in (self.start if isinstance(self.start, list) else [self.start]):
                trigger = start - self.lead
                a, b = max(trigger, n0), min(trigger + len(sample), n1)
                if a < b:
                    seg = sample[a - trigger: b - trigger]
                    if self.fade_in > 0:
                        env = _envelope(a, b, start, self.fade_in, None, 0)
                        seg = seg * (env[:, None] if seg.ndim == 2 else env)
                    out[a - n0: b - n0] += seg
            return out
        origin = self.start if self.start is not None else 0
        out = self.cycle[(np.arange(n0, n1) - origin + self.phase) % len(self.cycle)]
        env = _envelope(n0, n1, self.start, self.fade_in, self.end, self.fade_out)
        return out * (env[:, None] if out.ndim == 2 else env)


def dry_timeline(sample: np.ndarray, params: dict, rate: int, start: int | None, end: int | None,
                 n0: int, n1: int, source_id: str) -> np.ndarray:
    """Dry signal of one source over samples [n0, n1) (see ``DryGenerator``)."""
    return DryGenerator(sample, params, rate, start, end, source_id).window(n0, n1)
