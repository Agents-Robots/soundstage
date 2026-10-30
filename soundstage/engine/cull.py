"""Culling (FR-68): which sources and voices a render skips, chunk by chunk, within ``cull_db``.

Two stages, both with the energy-budget rule of ``soundstage.levels.skip_mask`` per group:

Decisions are made on blocks of ``BLOCK_S`` (the momentary-loudness window), so the budget holds
there and not only on average over a 4 s chunk; a voice skips a chunk when every block allows it.

1. ``before_setup``: an upper bound per source and block from the baked positions alone: the
   straight-line distance at every baked sample, mapped to its reception time by the travel time,
   the distance law, gain, send and the sample's highest 10 ms mean square. Cone, occlusion, pan
   and filters can only lower it. Sources whose bounds stay ``BOUND_MARGIN_DB`` below the budget in
   every block are not set up at all, which saves their setup time and memory.
2. ``plan``: for the voices that were set up, the estimate from the renderers (gains on the control
   grid, the share of the sample's spectrum the filters pass, the dry signal's energy: ``power``),
   summed per block; True where a voice renders.

Spec: docs/spec/signal-model.md#culling; model and measurements: research/models/culling.md, E16.
"""

from __future__ import annotations

import numpy as np

from soundstage.engine import signals
from soundstage.engine.control import ControlGrid
from soundstage.engine.scene import Scene, Source
from soundstage.levels import BOUND_MARGIN_DB, distance_gain, skip_mask

BLOCK_S = 0.4
"""Length of the blocks the culling rule is applied to (EBU R 128 momentary-loudness window)."""


def _activity(src: Source, scene: Scene, t: np.ndarray, length_s: float, slack: float) -> np.ndarray:
    """Where the source emits (1) at emission times ``t`` (s), widened by ``slack`` seconds."""
    p = src.params
    if p["mode"] == "once":
        triggers = p["frame"] if isinstance(p["frame"], list) else [p["frame"]]
        on = np.zeros(len(t), dtype=bool)
        for f in triggers:
            t0 = float(scene.seconds(f))
            on |= (t >= t0 - slack) & (t <= t0 + length_s + slack)
        return on.astype(np.float64)
    on = np.ones(len(t), dtype=bool)
    if p["frame"] is not None:
        on &= t >= float(scene.seconds(p["frame"])) - slack
    if p["end_frame"] is not None:
        on &= t <= float(scene.seconds(p["end_frame"])) + p["fade_out"] + slack
    return on.astype(np.float64)


def _per_chunk(r: np.ndarray, value: np.ndarray, edges_s: np.ndarray, reduce: str) -> np.ndarray:
    """Max or mean of ``value`` over the samples whose reception time ``r`` falls in each block;
    blocks without samples take the nearest block's value."""
    n = len(edges_s) - 1
    idx = np.searchsorted(edges_s, r, side="right") - 1
    ok = (idx >= 0) & (idx < n)
    out = np.zeros(n)
    count = np.zeros(n)
    if reduce == "max":
        np.maximum.at(out, idx[ok], value[ok])
    else:
        np.add.at(out, idx[ok], value[ok])
    np.add.at(count, idx[ok], 1)
    if reduce == "mean":
        out = np.divide(out, count, out=np.zeros(n), where=count > 0)
    have = np.nonzero(count > 0)[0]
    if len(have) == 0:
        whole = (value.max() if reduce == "max" else value.mean()) if len(value) else 0.0
        return np.full(n, whole)
    if len(have) < n:
        k = np.arange(n)
        j = np.searchsorted(have, k)
        left, right = have[np.clip(j - 1, 0, len(have) - 1)], have[np.clip(j, 0, len(have) - 1)]
        out = np.where(count > 0, out, out[np.where(k - left <= right - k, left, right)])
    return out


def estimates(scene: Scene, sources: list[Source], spans: list[tuple[int, int, int]],
              room_rolloff: float | None) -> tuple[np.ndarray, np.ndarray]:
    """Upper bound and estimate of each source's energy per decision block, (sources, blocks) each,
    from the baked positions alone (no setup): the straight-line distance mapped to its reception
    time, distance law, gain, send, and the sample's highest 10 ms (bound) or mean (estimate) mean
    square, while the source sounds. Cone, occlusion, pan and filters can only lower them."""
    s, rate = scene.settings, scene.sample_rate
    t = np.asarray(scene.seconds(scene.frames), dtype=np.float64)
    lpos = scene.listener_matrix[:, :3, 3]
    c = float(s["speed_of_sound"])
    slack = float(np.median(np.diff(t))) if len(t) > 1 else 0.0
    edges_s = np.array([a for a, _, _ in spans] + [spans[-1][1]], dtype=np.float64) / rate
    lengths = np.diff(edges_s)
    rear = max(1.0, 10.0 ** (s["rear_gain_db"] / 10.0)) if s["panner"] == "hybrid" else 1.0
    bound = np.zeros((len(sources), len(spans)))
    estimate = np.zeros((len(sources), len(spans)))
    for i, src in enumerate(sources):
        p = src.params
        ms_mean, ms_peak, length_s = signals.sample_stats(p["sample"])
        act = _activity(src, scene, t, length_s / p["pitch"], slack)
        g2 = 10.0 ** (p["gain_db"] / 10.0)
        if not src.spatial:  # reception time = emission time; counts towards its group's total
            estimate[i] = g2 * ms_mean * _per_chunk(t, act, edges_s, "mean") * lengths
            continue
        d = np.linalg.norm(scene.src_pos[:, src.track] - lpos, axis=1)
        pw = g2 * rear * distance_gain(d, p["distance_model"], p["ref_distance"], p["max_distance"], p["rolloff"]) ** 2
        if room_rolloff is not None:
            send_db = (p["reverb_send_db"] or 0.0) + s["reverb_send_db"]
            pw = pw + 10.0 ** ((p["gain_db"] + send_db) / 10.0) * distance_gain(
                d, p["distance_model"], p["ref_distance"], p["max_distance"], room_rolloff) ** 2
        pw = pw * act
        r = t + d / c
        bound[i] = ms_peak * _per_chunk(r, pw, edges_s, "max") * lengths
        estimate[i] = ms_mean * _per_chunk(r, pw, edges_s, "mean") * lengths
    return bound, estimate


def before_setup(scene: Scene, sources: list[Source], spans: list[tuple[int, int, int]], budget_db: float,
                 room_rolloff: float | None, levels: tuple[np.ndarray, np.ndarray] | None = None) -> np.ndarray:
    """Sources (bool, one per source) whose upper bound stays ``BOUND_MARGIN_DB`` below the budget
    in every decision block: they are skipped before setup. Beds are never skipped. ``levels``:
    the result of ``estimates`` when already computed."""
    bound, estimate = levels if levels is not None else estimates(scene, sources, spans, room_rolloff)
    spatial = np.array([src.spatial for src in sources], dtype=bool)
    skip = skip_mask(bound, [src.group for src in sources], budget_db - BOUND_MARGIN_DB, cullable=spatial,
                     totals=estimate)
    return skip.all(axis=1) & spatial


def blocks(chunks: list[tuple[int, int]], length: int) -> list[tuple[int, int, int]]:
    """Decision blocks (start, end, chunk index) of at most ``length`` samples within each chunk."""
    out = []
    for ci, (c0, c1) in enumerate(chunks):
        edges = list(range(c0, c1, max(1, length))) + [c1]
        out += [(a, b, ci) for a, b in zip(edges[:-1], edges[1:])]
    return out


def block_energy(power: list[np.ndarray], grid: ControlGrid, spans: list[tuple[int, int, int]]) -> np.ndarray:
    """Energy (voices, blocks) from per-control-point power on ``grid``."""
    samples = grid.samples
    lo = np.searchsorted(samples, [a for a, _, _ in spans])
    hi = np.searchsorted(samples, [b for _, b, _ in spans])
    out = np.zeros((len(power), len(spans)))
    for v, pw in enumerate(power):
        cum = np.concatenate([[0.0], np.cumsum(pw)])
        out[v] = (cum[hi] - cum[lo]) * grid.step
    return out


def per_chunk(skip: np.ndarray, spans: list[tuple[int, int, int]], n_chunks: int) -> np.ndarray:
    """(entries, chunks): skipped in a chunk only where skipped in every block of it."""
    chunk_of = np.array([ci for _, _, ci in spans])
    return np.stack([skip[:, chunk_of == ci].all(axis=1) for ci in range(n_chunks)], axis=1)


def plan(power: list[np.ndarray], groups: list[str], spatial: list[bool], grid: ControlGrid,
         spans: list[tuple[int, int, int]], n_chunks: int, budget_db: float) -> np.ndarray:
    """Which voices render in which chunk, (voices, chunks) bool: a voice is skipped in a chunk when
    the rule allows it in every decision block of the chunk."""
    energy = block_energy(power, grid, spans)
    skip = skip_mask(energy, groups, budget_db, cullable=np.asarray(spatial, dtype=bool))
    return ~per_chunk(skip, spans, n_chunks)
