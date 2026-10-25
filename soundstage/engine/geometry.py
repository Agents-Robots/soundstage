"""Trajectories and listener-relative geometry at control rate.

Phase 1: camera-space vectors ``q = R^T (s - p)`` are computed at the baked time samples and
interpolated linearly to the control rate, with a step (no interpolation) at camera cuts. Phase 2
replaces this with splines, retarded time and per-segment handling.

Blender camera axes: +X right, +Y up, -Z forward.
Spec: docs/spec/signal-model.md#coordinate-frames.
"""

from __future__ import annotations

import numpy as np

CONTROL_STEP = 48
"""Audio samples per control-rate step (1 kHz at 48 kHz)."""

R_MIN = 0.25
"""Near-field softening distance in metres (smooth pan when a source passes through the camera)."""


def camera_space(listener_matrix: np.ndarray, src_pos: np.ndarray) -> np.ndarray:
    """Camera-space vectors (N, S, 3) of source positions (N, S, 3) for listener matrices (N, 4, 4)."""
    rot = listener_matrix[:, :3, :3]
    rel = src_pos - listener_matrix[:, None, :3, 3]
    return np.einsum("nji,nsj->nsi", rot, rel)


def _knots(t: np.ndarray, values: np.ndarray, cut_times: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Insert a duplicate knot just before each cut so linear interpolation steps instead of sweeping."""
    for c in sorted(cut_times, reverse=True):
        j = int(np.searchsorted(t, c))
        if 0 < j < len(t):
            t = np.insert(t, j, t[j] - 1e-9)
            values = np.insert(values, j, values[j - 1], axis=0)
    return t, values


def interpolate(t_baked: np.ndarray, values: np.ndarray, t_out: np.ndarray, cut_times: np.ndarray) -> np.ndarray:
    """Linear interpolation of (N, ...) values to times t_out; held constant outside the baked range."""
    t, v = _knots(t_baked, values, cut_times)
    flat = v.reshape(len(t), -1)
    out = np.empty((len(t_out), flat.shape[1]))
    for i in range(flat.shape[1]):
        out[:, i] = np.interp(t_out, t, flat[:, i])
    return out.reshape((len(t_out),) + v.shape[1:])


def derived(q: np.ndarray) -> dict[str, np.ndarray]:
    """Distance and direction quantities from camera-space vectors (..., 3)."""
    r = np.linalg.norm(q, axis=-1)
    r_e = np.sqrt(r * r + R_MIN * R_MIN)
    return {
        "distance": r,
        "lateral": q[..., 0] / r_e,  # lateral sine, -1 left .. +1 right
        "rear": np.maximum(0.0, q[..., 2] / r_e),  # 0 front/side .. 1 behind
    }
