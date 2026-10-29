"""Culling in the bake (FR-68): visibility rays only for sources that may be heard.

At every visibility sample, ``Culler.keep`` estimates each spatial source's power at the listener:
gain, distance law at the distance of the sound heard now (retarded for the occluding sources),
the sample's level (its highest 10 ms mean square for the candidates, its mean square for the group
totals), one-shots only while they sound. The rule of ``soundstage.levels.skip_mask`` then skips,
per group, the quietest occluding sources ``BOUND_MARGIN_DB`` below ``cull_db``. ``fill`` gives the
skipped samples the visibility interpolated from the source's computed samples, so the scene file
keeps its format; whatever is filled in belongs to sources that contribute far below the budget.

Sample levels are read with Blender's ``aud`` module. Runs inside Blender (Blender's numpy only).
Spec: docs/spec/signal-model.md#culling.
"""

from __future__ import annotations

import numpy as np

from soundstage.blender.util import log
from soundstage.levels import BOUND_MARGIN_DB, distance_gain, skip_mask

ACTIVE_SLACK_S = 0.5
"""One-shots count as sounding this long before and after their sample (visibility smoothing)."""
STATS_BLOCK_S = 0.010

_levels: dict[str, tuple[float, float, float]] = {}


def sample_level(path: str) -> tuple[float, float, float]:
    """Mean square, highest 10 ms mean square and length in seconds of a sample's mono downmix."""
    if path not in _levels:
        import aud  # Blender's audio library: decodes WAV, FLAC, OGG

        sound = aud.Sound(path)
        rate = sound.specs[0]
        x = np.asarray(sound.data(), dtype=np.float64)
        x = x.mean(axis=1) if x.ndim == 2 else x
        sq = x * x
        if len(sq):
            block = max(1, int(round(STATS_BLOCK_S * rate)))
            peak = float((np.add.reduceat(sq, np.arange(0, len(sq), block)) / block).max())
            _levels[path] = (float(sq.mean()), peak, len(sq) / rate)
        else:
            _levels[path] = (0.0, 0.0, 0.0)
    return _levels[path]


class Culler:
    """Per visibility sample: which occluding sources get their visibility computed."""

    def __init__(self, spatial: list[dict], occluding: list[int], settings: dict, fps: float):
        self.occluding = np.asarray(occluding, dtype=np.int64)
        self.budget = settings["cull_db"] - BOUND_MARGIN_DB
        self.c = float(settings["speed_of_sound"])
        self.spatial = spatial
        self.groups = [s["group"] for s in spatial]
        mean, peak, self.windows = [], [], []
        for s in spatial:
            m, p, length = sample_level(s["sample"])
            mean.append(m)
            peak.append(p)
            if s["mode"] == "once":
                frames = s["frame"] if isinstance(s["frame"], list) else [s["frame"]]
                self.windows.append([(f / fps - ACTIVE_SLACK_S, f / fps + length / s["pitch"] + ACTIVE_SLACK_S)
                                     for f in frames])
            else:
                lo = -np.inf if s["frame"] is None else s["frame"] / fps - ACTIVE_SLACK_S
                hi = np.inf if s["end_frame"] is None else s["end_frame"] / fps + s["fade_out"] + ACTIVE_SLACK_S
                self.windows.append([(lo, hi)])
        g2 = np.array([10.0 ** (s["gain_db"] / 10.0) for s in spatial])
        self.mean, self.peak = g2 * np.array(mean), g2 * np.array(peak)
        self.cullable = np.zeros(len(spatial), dtype=bool)
        self.cullable[self.occluding] = True
        self.samples = 0
        self.skipped = 0

    def keep(self, t: float, listener_m: np.ndarray, emitted_m: np.ndarray, positions_m: np.ndarray) -> np.ndarray:
        """Indices into the occluding sources to compute at time ``t`` (s): ``emitted_m`` are their
        retarded positions, ``positions_m`` every spatial source's position now (metres)."""
        d = np.linalg.norm(positions_m - listener_m, axis=1)
        d[self.occluding] = np.linalg.norm(emitted_m - listener_m, axis=1)
        dg2 = np.array([distance_gain(dj, s["distance_model"], s["ref_distance"], s["max_distance"], s["rolloff"])
                        for dj, s in zip(d, self.spatial)], dtype=np.float64) ** 2
        te = t - d / self.c
        on = np.array([any(lo <= tj <= hi for lo, hi in w) for tj, w in zip(te, self.windows)], dtype=np.float64)
        skip = skip_mask(self.peak * dg2 * on, self.groups, self.budget, cullable=self.cullable,
                         totals=self.mean * dg2 * on)
        keep = np.nonzero(~skip[self.occluding])[0]
        self.samples += len(self.occluding)
        self.skipped += len(self.occluding) - len(keep)
        return keep

    def report(self) -> float:
        share = self.skipped / max(self.samples, 1)
        log(f"culling: visibility skipped for {100 * share:.0f} % of source samples "
            f"({self.budget + BOUND_MARGIN_DB:g} dB budget, {BOUND_MARGIN_DB:g} dB margin)")
        return share


def fill(vis: np.ndarray) -> np.ndarray:
    """Visibility (M, S, bands) with skipped samples (NaN) interpolated from each source's computed
    samples; a source never computed is open (1)."""
    out = vis.copy()
    idx = np.arange(len(vis))
    for j in range(vis.shape[1]):
        done = ~np.isnan(vis[:, j, 0])
        if done.all():
            continue
        for b in range(vis.shape[2]):
            out[:, j, b] = np.interp(idx, idx[done], vis[done, j, b]) if done.any() else 1.0
    return out
