"""Render orchestration: scene in, stereo buffer and statistics out.

Processes the output window in chunks (10 s). Per chunk and source: dry timeline, then for spatial
sources the control-rate geometry (distance gain, constant-power pan) upsampled to audio rate;
bed sources get gain only. Sources accumulate into the master.

Supports frame sub-ranges and solo/mute (FR-67). Phase 1: no propagation delay, Doppler, ear
model or filters. Data flow: docs/architecture.md#data-flow-inside-a-render.
"""

from __future__ import annotations

import fnmatch
import os
import time
from dataclasses import dataclass, field

import numpy as np

from soundstage.blender import schema
from soundstage.engine import filters, geometry, panning, signals
from soundstage.engine.scene import Scene, Source

CHUNK_BLOCKS = 10_000
"""Control blocks per chunk (10 s at 48 kHz)."""

AUDIBLE_DBFS = -60.0


@dataclass
class RenderResult:
    audio: np.ndarray  # (n, 2) float64
    rate: int
    frames: tuple[int, int]
    sources: list[dict]
    warnings: list[str] = field(default_factory=list)
    timing_s: dict = field(default_factory=dict)


def matches(source: Source, pattern: str) -> bool:
    """``group:NAME`` matches a group, anything else is a glob on the source id."""
    if pattern.startswith("group:"):
        return fnmatch.fnmatchcase(source.group, pattern[6:])
    return fnmatch.fnmatchcase(source.id, pattern)


def select(sources: list[Source], solo: list[str], mute: list[str]) -> list[Source]:
    out = [s for s in sources if not solo or any(matches(s, p) for p in solo)]
    return [s for s in out if not any(matches(s, p) for p in mute)]


def _active_frames(src: Source, sample_len: int, scene: Scene, fa: int, fb: int) -> list[float] | None:
    p, fps, rate = src.params, scene.fps, scene.sample_rate
    if p["mode"] == "once":
        triggers = p["frame"] if isinstance(p["frame"], list) else [p["frame"]]
        a, b = triggers[0], triggers[-1] + sample_len / rate * fps
    else:
        a = p["frame"] if p["frame"] is not None else fa
        b = p["end_frame"] + p["fade_out"] * fps if p["end_frame"] is not None else fb
    a, b = max(a, fa), min(b, fb)
    return [round(a, 2), round(b, 2)] if a <= b else None


def render(scene: Scene, frames: tuple[int, int] | None = None, solo: list[str] = (),
           mute: list[str] = ()) -> RenderResult:
    t_start = time.perf_counter()
    rate = scene.sample_rate
    fa, fb = frames or (scene.frame_start, scene.frame_end)
    n0 = scene.sample_of(fa)
    n1 = n0 + scene.length_samples(fa, fb)
    step = geometry.CONTROL_STEP
    warnings = list(scene.warnings)
    for key in schema.unimplemented(scene.manifest.get("settings", {}), schema.SCENE_SETTINGS):
        warnings.append(f"setting {key!r} is not implemented yet, ignored")

    active = select(scene.sources, list(solo), list(mute))
    samples = {}
    for s in active:
        samples[s.id] = signals.load_sample(s.params["sample"], rate, pitch=s.params["pitch"], stereo=not s.spatial)
        for key in schema.unimplemented(s.params, schema.SOURCE_KEYS):
            warnings.append(f"{s.id}: {key!r} is not implemented yet, ignored")
    t_loaded = time.perf_counter()

    t_baked = scene.seconds(scene.frames)
    cut_times = scene.seconds(scene.cuts)
    q_baked = geometry.camera_space(scene.listener_matrix, scene.src_pos)

    master = np.zeros((n1 - n0, 2))
    n_blocks = -(-(n1 - n0) // step)
    block_peak = {s.id: np.zeros(n_blocks) for s in active}
    dist_range = {s.id: [np.inf, -np.inf] for s in active if s.spatial}
    chunk = CHUNK_BLOCKS * step
    for c0 in range(n0, n1, chunk):
        c1 = min(c0 + chunk, n1)
        idx = np.arange(c0, c1)
        ctl = np.arange(c0, c1 + step, step)
        for s in active:
            p = s.params
            f = p["frame"]
            start = None if f is None else [scene.sample_of(x) for x in f] if isinstance(f, list) else scene.sample_of(f)
            end = scene.sample_of(p["end_frame"]) if p["end_frame"] is not None else None
            dry = signals.dry_timeline(samples[s.id], p, rate, start, end, c0, c1, s.id)
            gain = filters.db_to_gain(p["gain_db"])
            if s.spatial:
                q = geometry.interpolate(t_baked, q_baked[:, s.track], ctl / rate, cut_times)
                d = geometry.derived(q)
                g = gain * filters.distance_gain(d["distance"], p["distance_model"], p["ref_distance"],
                                                 p["max_distance"], p["rolloff"])
                gl, gr = panning.constant_power(d["lateral"])
                contrib = np.stack([dry * np.interp(idx, ctl, g * gl), dry * np.interp(idx, ctl, g * gr)], axis=1)
                r = dist_range[s.id]
                r[0], r[1] = min(r[0], d["distance"].min()), max(r[1], d["distance"].max())
            else:
                contrib = dry * gain
            master[c0 - n0: c1 - n0] += contrib
            peaks = np.abs(contrib).max(axis=1)
            b0 = (c0 - n0) // step
            block_peak[s.id][b0: b0 + -(-(c1 - c0) // step)] = np.maximum.reduceat(peaks, np.arange(0, c1 - c0, step))
    master *= filters.db_to_gain(scene.settings["master_gain_db"])
    t_dsp = time.perf_counter()

    # Block index of each frame boundary, for per-frame audibility.
    frame_blocks = [(scene.sample_of(f) - n0) // step for f in range(fa, fb + 2)]
    stats = []
    for s in active:
        bp = block_peak[s.id]
        audible = sum(
            1 for a, b in zip(frame_blocks[:-1], frame_blocks[1:])
            if b > a and filters.gain_to_db(bp[a:b].max()) > AUDIBLE_DBFS
        )
        st = {
            "id": s.id,
            "group": s.group,
            "sample": os.path.basename(s.params["sample"]),
            "mode": s.params["mode"],
            "spatial": s.spatial,
            "active_frames": _active_frames(s, len(samples[s.id]), scene, fa, fb),
            "peak_dbfs": round(float(filters.gain_to_db(bp.max() if len(bp) else 0.0)), 2),
            "audible_frames": audible,
        }
        if s.spatial:
            st["distance_m"] = [round(float(v), 2) for v in dist_range[s.id]]
        stats.append(st)
        if audible == 0:
            warnings.append(f"{s.id}: never audible (peak below {AUDIBLE_DBFS:g} dBFS in every frame)")
    return RenderResult(
        audio=master,
        rate=rate,
        frames=(fa, fb),
        sources=stats,
        warnings=warnings,
        timing_s={"load": round(t_loaded - t_start, 3), "dsp": round(t_dsp - t_loaded, 3)},
    )
