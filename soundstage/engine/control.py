"""Control-rate grid and interpolation from control points to audio samples.

Geometry and model parameters are evaluated on a uniform grid of reception times (one point every
``CONTROL_STEP`` output samples, 1 kHz at 48 kHz). Gains and filter parameters are interpolated
linearly per sample, delays with a cubic (Catmull-Rom) curve, so the read rate changes smoothly.

Spec: docs/spec/signal-model.md#trajectories-and-control-rate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from soundstage.engine import kernels

CONTROL_STEP = 48
"""Output samples per control step (1 kHz at 48 kHz)."""


@dataclass(frozen=True)
class ControlGrid:
    start: int  # output sample index of control point 0 (sample 0 = first frame of the shot)
    count: int
    rate: int  # output sample rate
    step: int = CONTROL_STEP

    @classmethod
    def covering(cls, n0: int, n1: int, rate: int, margin: int = 3, step: int = CONTROL_STEP) -> ControlGrid:
        """Grid over output samples [n0, n1) with ``margin`` extra points on each side."""
        start = n0 - margin * step
        count = -(-(n1 - start) // step) + margin + 1
        return cls(start=start, count=count, rate=rate, step=step)

    @property
    def samples(self) -> np.ndarray:
        return self.start + np.arange(self.count) * self.step

    @property
    def times(self) -> np.ndarray:
        """Reception times of the control points in seconds (0 = first frame)."""
        return self.samples / self.rate

    def index_of(self, sample: int) -> int:
        """Last control point at or before an output sample."""
        return int(np.clip((sample - self.start) // self.step, 0, self.count - 1))

    def _position(self, a: int, b: int) -> tuple[np.ndarray, np.ndarray]:
        u = (np.arange(a, b) - self.start) / self.step
        i = np.clip(np.floor(u).astype(np.int64), 0, self.count - 2)
        return i, np.clip(u - i, 0.0, 1.0)

    def _jump_mask(self, jumps) -> np.ndarray:
        mask = np.zeros(self.count + 2, dtype=np.uint8)
        if jumps is not None and len(jumps):
            mask[np.asarray(jumps, dtype=np.int64)] = 1
        return mask

    def linear(self, values: np.ndarray, a: int, b: int, jumps=None) -> np.ndarray:
        """Values (count, ...) at output samples [a, b), linearly interpolated.

        ``jumps``: control indices where a new segment starts; samples in the step before a jump
        take the new value, so nothing is interpolated across a jump.
        """
        mask = self._jump_mask(jumps)
        if values.ndim == 1:
            return kernels.control_linear(np.ascontiguousarray(values, dtype=np.float64), mask, self.start,
                                          self.step, a, np.empty(b - a))
        i, f = self._position(a, b)
        f = np.where(mask[i + 1] > 0, 1.0, f)
        f = f.reshape(f.shape + (1,) * (values.ndim - 1))
        return values[i] * (1.0 - f) + values[i + 1] * f

    def cubic(self, values: np.ndarray, a: int, b: int, jumps=None) -> np.ndarray:
        """Values (count,) at output samples [a, b), Catmull-Rom interpolated (ends clamped).

        ``jumps`` as in ``linear``; neighbours across a jump are replaced by the nearest value on
        the same side.
        """
        return kernels.control_cubic(np.ascontiguousarray(values, dtype=np.float64), self._jump_mask(jumps),
                                     self.start, self.step, a, np.empty(b - a))
