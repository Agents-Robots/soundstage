"""Level laws and the culling rule, shared by the bake (inside Blender) and the engine.

- ``distance_gain``: the distance models (as in OpenAL and Blender).
- ``skip_mask``: the culling rule. Per group and chunk, the quietest entries are skipped while
  their summed energy stays within ``10^(budget_db / 10)`` of the group's total, so the error of
  everything skipped stays within the budget however many quiet sources add up (a per-source
  threshold does not bound it). Entries that may not be skipped (beds) count towards the total.

numpy only (no bpy, no scipy), so both halves can import it (NFR-7).
Spec: docs/spec/signal-model.md#distance-gain, #culling; model: research/models/culling.md.
"""

from __future__ import annotations

import numpy as np

DISTANCE_MODELS = ("inverse_clamped", "linear_clamped", "exponential_clamped", "none")

BOUND_MARGIN_DB = 20.0
"""Upper-bound estimates (the render before setup, the bake) skip only this far below the budget."""


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


def skip_mask(energy: np.ndarray, groups: list, budget_db: float, cullable: np.ndarray | None = None,
              totals: np.ndarray | None = None) -> np.ndarray:
    """Entries to skip, (S, C) bool, from their energy (S, C) in C chunks (or (S,) for one chunk).

    ``groups`` (S labels): each group has its own budget. ``cullable`` (S,) bool: entries that may
    be skipped (default all). ``totals`` (S, C): energies the group totals are summed from, when
    they differ from the ones compared against the budget (upper bounds against estimates).
    Ties are broken by entry order, so the result is deterministic.
    """
    e = np.asarray(energy, dtype=np.float64)
    one = e.ndim == 1
    if one:
        e = e[:, None]
    tot = e if totals is None else np.asarray(totals, dtype=np.float64).reshape(e.shape)
    may = np.ones(len(e), dtype=bool) if cullable is None else np.asarray(cullable, dtype=bool)
    factor = 10.0 ** (budget_db / 10.0)
    labels = np.asarray([str(g) for g in groups], dtype=object)
    out = np.zeros(e.shape, dtype=bool)
    for g in dict.fromkeys(labels):
        members = labels == g
        cand = np.nonzero(members & may)[0]
        if not len(cand):
            continue
        limit = tot[members].sum(axis=0) * factor
        ec = e[cand]
        order = np.argsort(ec, axis=0, kind="stable")
        cum = np.cumsum(np.take_along_axis(ec, order, axis=0), axis=0)
        skip = np.zeros(ec.shape, dtype=bool)
        np.put_along_axis(skip, order, cum <= limit, axis=0)
        out[cand] = skip
    return out[:, 0] if one else out
