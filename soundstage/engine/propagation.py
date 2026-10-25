"""Propagation: read delays (Doppler, picture sync, ITD, rate clamp), interpolators, delay line.

- ``read_delays``: from the path's retarded delay to per-ear read delays. The Doppler factor ``k``
  scales the delay's variation around the reference delay ``tau0``; ``sync_to_picture`` drops
  ``tau0``; ITD offsets the ears by +-ITD/2. The playback rate ``1 - d tau_read/dt`` is clamped to
  [0.25, 4] and the delay re-integrated where the clamp applies, separately in every run between
  jumps so a cut is never smeared.
- Interpolators (registry ``INTERPOLATORS``, picked by the ``quality`` setting through
  ``QUALITY``): ``optimal2x`` (2x emission rate, pre-emphasis, 6-point polynomial), ``sinc``
  (anti-aliased windowed sinc at 1x), ``hermite4`` (reference).
- ``DelayLine``: emission samples produced on demand by the emission chain and trimmed behind the
  read positions.

Spec: docs/spec/signal-model.md#propagation-delay-doppler-itd; decisions: ADR 0006, ADR 0009.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

from soundstage.engine import kernels

RATE_MIN, RATE_MAX = 0.25, 4.0


@dataclass
class Delays:
    left: np.ndarray  # read delays per control point (s)
    right: np.ndarray
    centre: np.ndarray
    rate: np.ndarray  # playback rate 1 - d tau/dt per control point (centre)
    clamped: int  # control points where the rate was clamped


def _runs(n: int, jumps: np.ndarray) -> list[tuple[int, int]]:
    edges = [0, *[int(j) for j in jumps if 0 < j < n], n]
    return [(a, b) for a, b in zip(edges[:-1], edges[1:]) if b > a]


def read_delays(tau: np.ndarray, dt: float, jumps: np.ndarray, *, k: float, tau0: float, sync: bool,
                itd: np.ndarray | None = None, audible: np.ndarray | None = None) -> Delays:
    """Per-ear read delays on the control grid (spacing ``dt``) from the retarded delay ``tau``.

    ``audible``: where False (no retarded solution, e.g. after a teleport away) the rate is still
    clamped for a stable read, but not counted as clamped.
    """
    base = k * (tau - tau0) + (0.0 if sync else tau0)
    rate = np.ones_like(base)
    clamped = 0
    for a, b in _runs(len(base), jumps):
        if b - a < 2:
            continue
        r = 1.0 - np.gradient(base[a:b], dt)
        rc = np.clip(r, RATE_MIN, RATE_MAX)
        counted = (rc != r) if audible is None else (rc != r) & audible[a:b]
        n_clamped = int(np.sum(counted))
        if n_clamped:
            clamped += n_clamped
            steps = (1.0 - 0.5 * (rc[1:] + rc[:-1])) * dt
            base[a + 1:b] = base[a] + np.cumsum(steps)
        rate[a:b] = rc
    half = 0.5 * itd if itd is not None else 0.0
    return Delays(left=base + half, right=base - half, centre=base, rate=rate, clamped=clamped)


@dataclass(frozen=True)
class Interpolator:
    name: str
    oversample: int  # emission rate = output rate * oversample
    halfwidth: int  # emission samples needed on each side of a read position (worst case)
    read: Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray]  # (buf, pos, rate) -> samples
    prefilter: Callable[[], np.ndarray] | None = None  # FIR applied to the emission signal


def _read_optimal2x(buf, pos, rate):
    return kernels.read_optimal2x(buf, pos, np.empty(len(pos)))


def _read_hermite4(buf, pos, rate):
    return kernels.read_hermite4(buf, pos, np.empty(len(pos)))


_SINC_TABLE = kernels.sinc_table()


def _read_sinc(buf, pos, rate):
    return kernels.read_sinc(buf, pos, np.ascontiguousarray(rate), _SINC_TABLE, kernels.SINC_ZERO_CROSSINGS,
                             kernels.SINC_TABLE_PER_CROSSING, kernels.SINC_CUTOFF, np.empty(len(pos)))


INTERPOLATORS: dict[str, Interpolator] = {
    "optimal2x": Interpolator("optimal2x", 2, 4, _read_optimal2x, kernels.optimal2x_preemphasis),
    "sinc": Interpolator("sinc", 1,
                         math.ceil(kernels.SINC_ZERO_CROSSINGS * RATE_MAX / kernels.SINC_CUTOFF) + 1, _read_sinc),
    "hermite4": Interpolator("hermite4", 1, 3, _read_hermite4),
}
QUALITY = {"standard": "optimal2x", "high": "sinc"}


def interpolator_for(quality: str) -> Interpolator:
    return INTERPOLATORS[QUALITY[quality]]


class DelayLine:
    """Emission samples [start, end) produced on demand by ``produce(a, b)``."""

    def __init__(self, produce: Callable[[int, int], np.ndarray], start: int, block: int):
        self.produce = produce
        self.start = start
        self.buf = np.zeros(0)
        self.block = block

    @property
    def end(self) -> int:
        return self.start + len(self.buf)

    def ensure(self, end: int) -> None:
        if end > self.end:
            new_end = max(end, self.end + self.block)
            self.buf = np.concatenate([self.buf, self.produce(self.end, new_end)])

    def trim(self, before: int) -> None:
        if before > self.start:
            cut = min(before - self.start, len(self.buf))
            self.buf = self.buf[cut:]
            self.start += cut

    def read(self, interp: Interpolator, pos: np.ndarray, rate: np.ndarray) -> np.ndarray:
        """Read at emission positions (fractional emission sample indices)."""
        if len(pos) == 0:
            return np.zeros(0)
        self.ensure(int(math.ceil(pos.max())) + interp.halfwidth + 1)
        return interp.read(self.buf, pos - self.start, rate)
