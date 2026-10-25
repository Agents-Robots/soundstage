"""Gain laws, cutoff laws and time-varying filter kernels.

Phase 1: distance models (inverse, linear, exponential clamped, none), as in OpenAL and Blender.
Later phases add the directivity cone, rear cue, occlusion, air absorption and the filter kernels.

Spec: docs/spec/signal-model.md#distance-gain.
"""

from __future__ import annotations

import numpy as np


def db_to_gain(db: float | np.ndarray) -> float | np.ndarray:
    return 10.0 ** (np.asarray(db) / 20.0)


def gain_to_db(gain: float | np.ndarray, floor: float = -200.0) -> float | np.ndarray:
    g = np.maximum(np.abs(np.asarray(gain, dtype=np.float64)), 10.0 ** (floor / 20.0))
    return 20.0 * np.log10(g)


def distance_gain(d: np.ndarray, model: str, ref: float, max_distance: float | None, rolloff: float) -> np.ndarray:
    """Linear gain for distances ``d`` (metres); 1 at and inside the reference distance."""
    d = np.asarray(d, dtype=np.float64)
    hi = np.inf if max_distance is None else max_distance
    dc = np.clip(d, ref, hi)
    if model == "inverse_clamped":
        return ref / (ref + rolloff * (dc - ref))
    if model == "linear_clamped":
        return np.maximum(0.0, 1.0 - rolloff * (dc - ref) / (hi - ref)) if hi > ref else np.ones_like(dc)
    if model == "exponential_clamped":
        return (dc / ref) ** (-rolloff)
    if model == "none":
        return np.ones_like(dc)
    raise ValueError(f"unknown distance model {model!r}")
