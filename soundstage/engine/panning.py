"""Panners.

Phase 1: constant-power amplitude panning from the lateral sine of the source direction. The
``hybrid`` panner (default setting) adds ITD and head shadow in Phase 2; until then it pans like
``amplitude``. ``binaural`` follows in Phase 4.

Spec: docs/spec/signal-model.md#panning; decision: ADR 0007.
"""

from __future__ import annotations

import numpy as np


def constant_power(lateral: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Left and right gains for lateral sines in [-1, 1]; gL^2 + gR^2 = 1, centre -3.01 dB each."""
    phi = (np.clip(lateral, -1.0, 1.0) + 1.0) * (np.pi / 4.0)
    return np.cos(phi), np.sin(phi)
