"""Far field (level of detail, FR-56): sources outside the ``detail_voices`` loudest of their group.

Each far voice costs one interpolated read and a few multiply-adds per output sample
(``kernels.far_mix``): the dry signal is read from a buffer shared by all voices of the same sample
(pitch, Doppler and travel delay combined in the read position), scaled by its gains and amplitude
pan, and added into per-group buses. The buses cluster the voices by distance and occlusion, not by
direction: one bus per distance band (no air absorption, then 25 m to 12.8 km, sqrt(2) apart), open
and occluded. A voice's contribution is split between the two bands around its distance (weights
linear in log distance) and between open (visibility v) and occluded (1 - v, times the
transmission gain), so nothing switches; each bus is filtered once per chunk by the air absorption
of its band distance (and the occluded buses by the transmission low-pass). The reverb send goes to
one mono bus per band, filtered by the band's air absorption as well.

What the far field leaves out, compared with the full chain (``source.SpatialRenderer``): ITD, head
shadow, the rear low-pass (the rear cue stays as a level), the per-band occlusion low-pass, and the
occlusion low-pass of the send in ``occlusion`` mode (its gain stays). Geometry is computed per chunk
from the baked positions (linear between baked samples, retarded delay by fixed-point steps):
nothing is kept per voice over the whole shot. Jumps (camera cuts, teleports) fade the voice out and in over ``JUMP_FADE_CTL``
control points instead of crossfading a held branch.

Spec: docs/spec/signal-model.md#far-field; model: research/models/level-of-detail.md; ADR 0013.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from soundstage.engine import filters, geometry, kernels, panning, signals
from soundstage.engine.scene import Scene, Source

OVERSAMPLE = 2
"""The far field reads with the optimal-2x interpolator from buffers at twice the output rate."""
BAND_FIRST_M = 25.0
BAND_RATIO = math.sqrt(2.0)
N_BANDS = 20
"""Bus 0 has no air absorption; bus k >= 1 has the air absorption of 25 m * sqrt(2)^(k - 1) (25 m ... 12.8 km).
A voice between two bands is the sum of their filters, whose phases differ: where the loss is below
20 dB it stays within 0.73 dB of the full chain up to 6.5 kHz sqrt(2) apart, 2.2 dB an octave apart (E05)."""
TIER_FADE_S = 0.1
"""Equal-power crossfade between the tiers when a source changes tier at a chunk boundary."""
COARSE = 4
"""Control points between two evaluations of the far field's geometry (interpolated in between)."""
JUMP_FADE_CTL = 8
"""Control points over which a voice fades out before and in after a jump (cut, teleport); more
than ``COARSE``, so the fade covers the interpolation across the jump."""
CULL_RAMP_CTL = 10
"""Control points of the gain ramp into and out of a block skipped by culling."""
FIXED_POINT_STEPS = 6
TASKS = 16
"""Worker tasks per group and chunk, each with its own buses and bus filter states (fixed, so the
output does not depend on the number of workers)."""
BATCH = 64
"""Voices whose control arrays a task computes at once."""
MIX_BLOCK = 1024
"""Output samples ``far_mix`` adds every voice of a batch into before moving on (cache-sized buses)."""


def coherence(params: dict, panner: str) -> float:
    """Expected correlation of a source's near and far renders, for the crossfade law: the same dry
    signal and phase at pitch 1 (the amplitude panner: identical but for the filters; the hybrid
    panner's ITD and head shadow decorrelate the highs), unrelated loop phases otherwise."""
    if params["pitch"] != 1.0:
        return 0.0
    return 1.0 if panner == "amplitude" else 0.5


def crossfade(u: np.ndarray, rho: float) -> tuple[np.ndarray, np.ndarray]:
    """Gains in and out over u in [0, 1] that keep the level of two signals with correlation rho
    (a^2 + b^2 + 2 rho a b = 1, as the loop seam in ``signals.loop_cycle``)."""
    u = np.clip(u, 0.0, 1.0)
    a, b = np.sin(0.5 * np.pi * u), np.cos(0.5 * np.pi * u)
    norm = 1.0 / np.sqrt(a * a + b * b + 2.0 * rho * a * b)
    return a * norm, b * norm


HYSTERESIS = 1.5
"""A near source stays near while it ranks within this many times ``detail_voices`` in its group."""


def assign_tiers(energy: np.ndarray, groups: list[str], spatial: np.ndarray, spans: list[tuple[int, int, int]],
                 n_chunks: int, detail: int) -> np.ndarray:
    """Near (True) or far, per source and chunk (sources, chunks), from the estimated energy per
    decision block (sources, blocks): per group, the ``detail`` sources with the most energy in a
    chunk are near (and stay near while they rank within ``HYSTERESIS * detail``); silent ones are
    far. Beds are always near."""
    chunk_of = np.array([ci for _, _, ci in spans], dtype=np.int64)
    per_chunk = np.zeros((len(energy), n_chunks))
    for ci in range(n_chunks):
        per_chunk[:, ci] = energy[:, chunk_of == ci].sum(axis=1)
    near = np.ones((len(energy), n_chunks), dtype=bool)
    labels = np.asarray([str(g) for g in groups], dtype=object)
    for g in dict.fromkeys(labels):
        idx = np.nonzero((labels == g) & spatial)[0]
        if len(idx) <= detail:
            continue
        prev = np.zeros(len(idx), dtype=bool)
        for ci in range(n_chunks):
            e = per_chunk[idx, ci]
            rank = np.empty(len(idx), dtype=np.int64)
            rank[np.argsort(-e, kind="stable")] = np.arange(len(idx))
            now = ((rank < detail) | (prev & (rank < HYSTERESIS * detail))) & (e > 0)
            near[idx, ci] = now
            prev = now
    return near


def band_distances() -> np.ndarray:
    return np.concatenate([[0.0], BAND_FIRST_M * BAND_RATIO ** np.arange(N_BANDS - 1)])


def band_weights(distance: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Lower band index (n,) and the weight (n,) of the band above it, for distances in metres:
    linear in distance below the first band, linear in log distance above, held at the last."""
    d = np.maximum(np.asarray(distance, dtype=np.float64), 0.0)
    pos = np.where(d < BAND_FIRST_M, d / BAND_FIRST_M,
                   1.0 + np.log(np.maximum(d, BAND_FIRST_M) / BAND_FIRST_M) / math.log(BAND_RATIO))
    pos = np.minimum(pos, N_BANDS - 1)
    lo = np.minimum(np.floor(pos).astype(np.int64), N_BANDS - 2)
    return lo, pos - lo


def _catmull_rom(v: np.ndarray, k: np.ndarray, f: np.ndarray) -> np.ndarray:
    """Catmull-Rom interpolation of rows of ``v`` (m, B) at rows k + f (k (n,), f (n, 1)); ends held."""
    m = len(v)
    y0, y1 = v[k], v[k + 1]
    ym1 = v[np.maximum(k - 1, 0)]
    y2 = v[np.minimum(k + 2, m - 1)]
    c1 = 0.5 * (y1 - ym1)
    c2 = ym1 - 2.5 * y0 + 2.0 * y1 - 0.5 * y2
    c3 = 0.5 * (y2 - ym1) + 1.5 * (y0 - y1)
    return ((c3 * f + c2) * f + c1) * f + y0


@dataclass
class Buffer:
    data: np.ndarray  # at OVERSAMPLE x the output rate, prefiltered; loops padded with the cycle's ends
    period: float  # loop cycle length in samples (0: one-shot)
    offset: int  # loops: where the cycle starts in ``data``; one-shots: the prefilter's lead


class Buffers:
    """Dry buffers shared by every far voice with the same sample, mode and loop crossfade."""

    def __init__(self, rate: int):
        self.rate = rate * OVERSAMPLE
        self.prefilter = kernels.optimal2x_preemphasis()
        self.cache: dict[tuple, Buffer] = {}

    def get(self, params: dict) -> Buffer:
        loop = params["mode"] == "loop"
        key = (params["sample"], loop, params["loop_crossfade"] if loop else 0.0)
        if key not in self.cache:
            x = signals.load_sample(params["sample"], self.rate)
            m = len(self.prefilter) // 2
            if loop:
                cycle = signals.loop_cycle(x, int(round(params["loop_crossfade"] * self.rate)))
                wrapped = np.concatenate([cycle[-m:], cycle, cycle[:m]]) if m else cycle
                cycle = np.convolve(wrapped, self.prefilter, mode="valid")
                pad = 4
                data = np.concatenate([cycle[-pad:], cycle, cycle[:pad]])
                self.cache[key] = Buffer(np.ascontiguousarray(data), float(len(cycle)), pad)
            else:
                self.cache[key] = Buffer(np.ascontiguousarray(np.convolve(x, self.prefilter)), 0.0, m)
        return self.cache[key]


@dataclass
class Voice:
    """One far voice: a loop, or one trigger of a one-shot."""

    source: int  # index into the render's active sources
    track: int
    params: dict
    group: str
    buffer: Buffer
    origin: float  # emission index (at the far rate) where the dry signal starts
    phase: float  # buffer position at ``origin``
    k: float  # Doppler factor
    sync: bool
    tau0: float = 0.0
    follow: np.ndarray | None = None  # smoothed visibility per band, carried between chunks
    stats: dict = field(default_factory=dict)


@dataclass
class Part:
    """A far voice's share of a chunk: tier fades and the culling gate."""

    voice: int
    fade_in: bool = False  # the source was near in the previous chunk: crossfade in at the start
    fade_out: bool = False  # the source is near from this chunk on: only the crossfade out at the start
    gate: np.ndarray | None = None  # per decision block of the chunk: False where culling skips it


class FarField:
    def __init__(self, scene: Scene, ctx, sources: list[Source], indices: list[int]):
        """Far voices of ``sources[i]`` for ``i`` in ``indices`` (spatial sources only)."""
        s = scene.settings
        self.scene, self.ctx, self.grid, self.geo = scene, ctx, ctx.grid, ctx.geometry
        self.rate = ctx.rate
        self.fe = self.rate * OVERSAMPLE
        self.c = float(s["speed_of_sound"])
        self.buffers = Buffers(self.rate)
        self.times = np.asarray(scene.seconds(scene.frames), dtype=np.float64)
        self.law = panning.PAN_LAWS[s["pan_law"]]
        self.rear_cue = ctx.panner.rear_cue
        self.voices: list[Voice] = []
        self.by_source: dict[int, list[int]] = {}
        for i in indices:
            src = sources[i]
            p = src.params
            buf = self.buffers.get(p)
            k = float(s["doppler_factor"] * p["doppler"])
            triggers = (p["frame"] if isinstance(p["frame"], list) else [p["frame"]]) if p["mode"] == "once" else [p["frame"]]
            for f in triggers:
                origin = 0.0 if f is None else float(scene.seconds(f)) * self.fe
                phase = float(buf.offset)
                if buf.period:
                    if p["loop_phase"] == "random":
                        phase = float(np.random.default_rng(signals.seed_for(src.id)).integers(0, int(buf.period)))
                    else:
                        phase = float(round(p["loop_phase"] * self.fe) % buf.period)
                v = Voice(source=i, track=src.track, params={**p, "frame": f}, group=src.group, buffer=buf,
                          origin=origin, phase=phase, k=k, sync=bool(p["sync_to_picture"]) and p["mode"] == "once")
                self.by_source.setdefault(i, []).append(len(self.voices))
                self.voices.append(v)
        self._reference_delays()
        # every buffer in one array, and the per-voice read parameters as arrays (for far_mix)
        starts, parts_, at = {}, [], 0
        for key, buf in self.buffers.cache.items():
            starts[key] = at
            parts_.append(buf.data)
            at += len(buf.data)
        self.bufcat = np.concatenate(parts_) if parts_ else np.zeros(1)
        index = {id(buf): starts[key] for key, buf in self.buffers.cache.items()}
        self.v_start = np.array([index[id(v.buffer)] for v in self.voices], dtype=np.int64)
        self.v_len = np.array([len(v.buffer.data) for v in self.voices], dtype=np.int64)
        self.v_period = np.array([v.buffer.period for v in self.voices], dtype=np.float64)
        self.v_offset = np.array([float(v.buffer.offset) if v.buffer.period else 0.0 for v in self.voices])
        self.v_origin = np.array([v.origin for v in self.voices], dtype=np.float64)
        self.v_pitch = np.array([float(v.params["pitch"]) for v in self.voices], dtype=np.float64)
        self.v_phase = np.array([v.phase for v in self.voices], dtype=np.float64)
        self.tracks = np.array(sorted({v.track for v in self.voices}), dtype=np.int64)
        # teleports per track: speed between two baked samples above the teleport speed
        self.teleport = np.zeros((max(len(self.times) - 1, 0), scene.src_pos.shape[1]), dtype=bool)
        max_speed = float(s["teleport_speed"] or geometry.TELEPORT_FACTOR * self.c)
        dt = np.diff(self.times)
        for a in range(0, len(self.tracks), 512):
            tr = self.tracks[a:a + 512]
            speed = np.linalg.norm(np.diff(scene.src_pos[:, tr], axis=0), axis=2) / dt[:, None]
            self.teleport[:, tr] = speed > max_speed
        seg = self.geo.segment
        self.cut = np.zeros(self.grid.count, dtype=bool)
        self.cut[1:] = seg[1:] != seg[:-1]
        self.cut[:-1] |= self.cut[1:]
        # buses: distance bands x (open, occluded), and the send per band; filters per group, states
        # carried between chunks
        air = filters.AirAbsorption(s["air_temperature_c"], s["air_humidity_pct"], self.rate,
                                    scale=s["air_absorption"])
        self.bus_air = [None if air.bypass(np.array([d])) else
                        np.ascontiguousarray(kernels.svf_coefficients(air.params(np.array([d]))[0]))
                        for d in band_distances()]  # (sections, 5) per band; None: no filtering
        self.occ_gain = float(filters.tpt_gain(np.array([float(s["occlusion_cutoff_hz"])]), self.rate)[0])
        self.transmission = float(filters.db_to_gain(s["occlusion_gain_db"]))
        self.states: dict[tuple[str, int], dict[str, np.ndarray]] = {}  # (group, task) -> filter states
        self.send = ctx.send

    # ---------------------------------------------------------------- geometry

    def _positions(self, te: np.ndarray, tracks: np.ndarray) -> np.ndarray:
        """Source positions (n, B, 3) at emission times te (n, B), linear between baked samples."""
        times, pos = self.times, self.scene.src_pos
        if len(times) < 2:
            return np.broadcast_to(pos[0, tracks], te.shape + (3,)).copy()
        idx = np.clip(np.searchsorted(times, te, side="right") - 1, 0, len(times) - 2)
        f = np.clip((te - times[idx]) / (times[idx + 1] - times[idx]), 0.0, 1.0)[..., None]
        a = pos[idx, tracks[None, :]]
        return a + (pos[idx + 1, tracks[None, :]] - a) * f

    def retarded(self, t: np.ndarray, p: np.ndarray, tracks: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Retarded delay (n, B) and emitting position (n, B, 3) for reception times t (n,) at
        listener positions p (n, 3)."""
        te = np.broadcast_to(t[:, None], (len(t), len(tracks)))
        s = self._positions(te, tracks)
        tau = np.linalg.norm(s - p[:, None, :], axis=2) / self.c
        for _ in range(FIXED_POINT_STEPS):
            s = self._positions(t[:, None] - tau, tracks)
            tau = np.linalg.norm(s - p[:, None, :], axis=2) / self.c
        return tau, s

    def _delays_at(self, t: np.ndarray, tracks: np.ndarray) -> np.ndarray:
        """Retarded delay of track ``tracks[i]`` heard at time ``t[i]`` (pairwise)."""
        p, _, _ = self.geo.listener.pose(t)
        s = self._positions(t[None, :], tracks)[0]
        tau = np.linalg.norm(s - p, axis=1) / self.c
        for _ in range(FIXED_POINT_STEPS):
            s = self._positions((t - tau)[None, :], tracks)[0]
            tau = np.linalg.norm(s - p, axis=1) / self.c
        return tau

    def _reference_delays(self) -> None:
        """tau0 per voice, as ``SpatialRenderer._reference_delay``: the delay heard at the trigger or
        loop start (at the shot start when there is none)."""
        if not self.voices:
            return
        tracks = np.array([v.track for v in self.voices], dtype=np.int64)
        has = np.array([v.params["frame"] is not None for v in self.voices])
        t_emit = np.array([float(self.scene.seconds(v.params["frame"])) if v.params["frame"] is not None else 0.0
                           for v in self.voices])
        t = t_emit.copy()
        for _ in range(6):  # reception time t with t - tau(t) = t_emit
            t = np.where(has, t_emit + self._delays_at(t, tracks), 0.0)
        for v, tau in zip(self.voices, self._delays_at(t, tracks)):
            v.tau0 = float(tau)

    # ---------------------------------------------------------------- one chunk

    def _jump_mask(self, bad: np.ndarray) -> np.ndarray:
        """1 away from bad control points, 0 on them, a raised-cosine ramp over JUMP_FADE_CTL."""
        n = bad.shape[0]
        if not bad.any():
            return np.ones(bad.shape)
        idx = np.arange(n)[:, None]
        last = np.maximum.accumulate(np.where(bad, idx, -10 ** 9), axis=0)
        nxt = np.minimum.accumulate(np.where(bad, idx, 10 ** 9)[::-1], axis=0)[::-1]
        d = np.minimum(idx - last, nxt - idx)
        u = np.clip(d / JUMP_FADE_CTL, 0.0, 1.0)
        return 0.5 - 0.5 * np.cos(np.pi * u)

    def _distance_gains(self, distance: np.ndarray, prms: list[dict], rolloff: float | None = None) -> np.ndarray:
        """Distance-law gains (n, B) for the voices' parameters (``rolloff``: the room rolloff of
        the reverb send instead of each voice's own)."""
        out = np.empty_like(distance)
        models = np.array([p["distance_model"] for p in prms])
        for model in dict.fromkeys(models):
            cols = np.nonzero(models == model)[0]
            ref = np.array([prms[c]["ref_distance"] for c in cols])
            hi = np.array([np.inf if prms[c]["max_distance"] is None else prms[c]["max_distance"] for c in cols])
            ro = np.full(len(cols), rolloff) if rolloff is not None else np.array([prms[c]["rolloff"] for c in cols])
            if model in ("inverse_clamped", "exponential_clamped", "none"):
                dc = np.clip(distance[:, cols], ref, hi)
                out[:, cols] = (ref / (ref + ro * (dc - ref)) if model == "inverse_clamped"
                                else (dc / ref) ** (-ro) if model == "exponential_clamped" else 1.0)
            else:
                for k, c in enumerate(cols):
                    out[:, c] = filters.distance_gain(distance[:, c], model, ref[k], prms[c]["max_distance"], ro[k])
        return out

    def _control(self, ids: list[int], parts: list[Part], j0: int, j1: int, c0: int, c1: int, spans):
        """Control arrays over control points j0..j1 for the voices ``ids``, vectorized over them:
        emission index e, gains left, right and send (B, n), lower band (B, n), bus weights
        (B, n, 4), the weight of the band above (B, n), and which voices sound at all (B,)."""
        grid, geo, s = self.grid, self.geo, self.scene.settings
        J = np.arange(j0, j1 + 1)
        t = grid.times[J]
        voices = [self.voices[i] for i in ids]
        prms = [v.params for v in voices]
        tracks = np.array([v.track for v in voices], dtype=np.int64)
        # geometry every COARSE control points, interpolated (the delay with Catmull-Rom, so the
        # playback rate stays smooth; direction and distance linearly)
        jc = j0 + COARSE * np.arange((j1 - j0) // COARSE + 2)
        jh = np.minimum(jc, grid.count - 1)
        tc = (grid.start + jc * grid.step) / grid.rate
        pc, rotc = geo.p[jh], geo.rot[jh]
        tau_c, pos_c = self.retarded(tc, pc, tracks)
        qc = np.einsum("nji,nbj->nbi", rotc, pos_c - pc[:, None, :])
        nc, b = tau_c.shape
        flat = qc.reshape(-1, 3)
        dc = geometry.derived(flat)
        if geo.frame is not None:
            fl, fr = geo.frame[0][jh], geo.frame[1][jh]
            lat_c = panning.screen_lateral(flat, np.repeat(fl, b), np.repeat(fr, b), s["screen_edge_deg"],
                                           self.law, geometry.R_MIN).reshape(nc, b)
        else:
            lat_c = dc["lateral"].reshape(nc, b)
        te_c = tc[:, None] - tau_c
        k_tel = np.clip(np.searchsorted(self.times, te_c, side="right") - 1, 0, max(len(self.times) - 2, 0))
        bad_c = self.teleport[k_tel, tracks[None, :]] if len(self.teleport) else np.zeros((nc, b), dtype=bool)
        x = (J - j0) / COARSE
        kc = np.minimum(np.floor(x).astype(np.int64), nc - 2)
        f = (x - kc)[:, None]
        tau = _catmull_rom(tau_c, kc, f)
        lateral = lat_c[kc] + (lat_c[kc + 1] - lat_c[kc]) * f
        rear_c = dc["rear"].reshape(nc, b)
        rear = rear_c[kc] + (rear_c[kc + 1] - rear_c[kc]) * f
        pos = pos_c[kc] + (pos_c[kc + 1] - pos_c[kc]) * f[..., None]
        p = geo.p[J]
        n = len(J)
        distance = self.c * tau
        te = t[:, None] - tau
        # jumps: a teleport near either coarse neighbour, a camera cut within the coarse interval
        cut_fine = self.cut[J]
        cut_c = np.zeros(nc, dtype=bool)
        np.logical_or.at(cut_c, np.minimum((J - j0) // COARSE, nc - 1), cut_fine)
        bad = bad_c[kc] | bad_c[kc + 1] | cut_c[kc][:, None]
        k = np.array([v.k for v in voices])
        tau0 = np.array([v.tau0 for v in voices])
        sync = np.array([v.sync for v in voices])
        tau_read = k * (tau - tau0) + np.where(sync, 0.0, tau0)
        e = (t[:, None] - tau_read) * self.fe
        ts = grid.samples[J]
        # gains common to the stereo output and the send
        common = self._jump_mask(bad)
        fade = int(round(TIER_FADE_S * self.rate))
        block_of = None
        for col, (v, pt) in enumerate(zip(voices, parts)):
            prm = v.params
            if prm["mode"] == "once" and (prm["fade_in"] or 0.0) > 0 or prm["mode"] == "loop" and (
                    prm["frame"] is not None or prm["end_frame"] is not None):
                common[:, col] *= self._envelope(v, e[:, col])
            if pt.fade_in or pt.fade_out:
                fin, fout = crossfade((ts - c0) / fade, coherence(prm, s["panner"]))
                common[:, col] *= fin if pt.fade_in else fout
            if pt.gate is not None:
                if block_of is None:
                    starts = np.array([a for a, _, _ in spans])
                    block_of = np.clip(np.searchsorted(starts, ts, side="right") - 1, 0, len(spans) - 1)
                common[:, col] *= self._ramp(pt.gate[block_of].astype(np.float64))
            if prm["cone_inner_deg"] < 360.0 or prm["cone_outer_deg"] < 360.0:
                common[:, col] *= self._cone(v, te[:, col], pos[:, col] - p, prm)
        level = 10.0 ** (np.array([prm["gain_db"] for prm in prms]) / 20.0)
        g = common * level * self._distance_gains(distance, prms)
        if self.rear_cue:
            g = g * filters.rear_gain(rear, s["rear_gain_db"])
        sounds = np.any(g != 0.0, axis=0)
        open_w = np.ones((n, b))
        sc = self.scene
        if sc.src_visibility is not None and sc.vis_frames is not None and len(sc.vis_frames):
            vt = sc.seconds(sc.vis_frames)
            for col, v in enumerate(voices):
                if v.params["occlusion"] and sounds[col]:
                    vis = np.stack([np.interp(t, vt, sc.src_visibility[:, v.track, band])
                                    for band in range(sc.src_visibility.shape[2])], axis=1)
                    open_w[:, col] = self._follow(v, vis).mean(axis=1)
        occ_w = (1.0 - open_w) * self.transmission
        gl, gr = self.law(lateral)
        air = np.array([prm["air_absorption"] for prm in prms])
        lo, frac = band_weights(distance * air)
        w = np.stack([(1.0 - frac) * open_w, frac * open_w, (1.0 - frac) * occ_w, frac * occ_w], axis=2)
        gs = np.zeros((n, b))
        if self.send is not None:
            send_db = np.array([(prm["reverb_send_db"] or 0.0) for prm in prms]) + s["reverb_send_db"]
            gs = common * 10.0 ** ((send_db + np.array([prm["gain_db"] for prm in prms])) / 20.0) * \
                self._distance_gains(distance, prms, self.send.room_rolloff) * self.send.factor(distance)
            mode = np.array([prm["occlusion_mode"] == "occlusion" for prm in prms])
            gs = np.where(mode, gs * (open_w + occ_w), gs)
            sounds |= np.any(gs != 0.0, axis=0)
        inside = (ts >= c0) & (ts < c1)
        if inside.any():
            dt = grid.step / grid.rate
            rate = 1.0 - np.gradient(tau_read, dt, axis=0) if n > 1 else np.ones((1, b))
            ranges = {key: (x[inside].min(axis=0), x[inside].max(axis=0))
                      for key, x in (("distance", distance), ("delay", tau_read), ("rate", rate))}
            for col, v in enumerate(voices):
                if not sounds[col]:
                    continue
                for key, (lo_, hi_) in ranges.items():
                    st = v.stats.get(key)
                    v.stats[key] = (min(st[0], lo_[col]), max(st[1], hi_[col])) if st else (lo_[col], hi_[col])
        return (np.ascontiguousarray(e.T), np.ascontiguousarray((g * gl).T), np.ascontiguousarray((g * gr).T),
                np.ascontiguousarray(gs.T), np.ascontiguousarray(lo.T), np.ascontiguousarray(w.transpose(1, 0, 2)),
                np.ascontiguousarray(frac.T), sounds)

    def _ramp(self, on: np.ndarray) -> np.ndarray:
        """Gate (0/1 per control point) with raised-cosine ramps of CULL_RAMP_CTL on the 'on' side."""
        if on.all() or not on.any():
            return on
        idx = np.arange(len(on))
        last = np.maximum.accumulate(np.where(on == 0, idx, -10 ** 9))
        nxt = np.minimum.accumulate(np.where(on == 0, idx, 10 ** 9)[::-1])[::-1]
        u = np.clip(np.minimum(idx - last, nxt - idx) / CULL_RAMP_CTL, 0.0, 1.0)
        return 0.5 - 0.5 * np.cos(np.pi * u)

    def _envelope(self, v: Voice, e: np.ndarray) -> np.ndarray:
        """Fades at emission indices e (at the far rate): one-shots their fade-in, loops their
        start and end fades (as ``signals.DryGenerator``)."""
        prm, fe = v.params, self.fe
        env = np.ones(len(e))
        if prm["mode"] == "once":
            fi = (prm["fade_in"] or 0.0) * fe
            if fi > 0:
                env = np.where(e < v.origin, 1.0, signals.raised_cosine_at(np.clip((e - v.origin) / fi, 0.0, 1.0)))
            return env
        if prm["frame"] is not None:
            fi = prm["fade_in"] * fe
            start = v.origin
            env = np.where(e < start, 0.0, signals.raised_cosine_at(np.clip((e - start) / fi, 0.0, 1.0)) if fi > 0
                           else 1.0)
        if prm["end_frame"] is not None:
            end = float(self.scene.seconds(prm["end_frame"])) * fe
            fo = prm["fade_out"] * fe
            env = env * (np.where(e >= end, 0.0, 1.0) if fo <= 0
                         else signals.raised_cosine_at(np.clip(1.0 - (e - end) / fo, 0.0, 1.0)))
        return env

    def _cone(self, v: Voice, te: np.ndarray, rel: np.ndarray, prm: dict) -> np.ndarray:
        fwd = self.scene.src_fwd
        if fwd is None:
            return np.ones(len(te))
        idx = np.clip(np.searchsorted(self.times, te, side="right") - 1, 0, len(self.times) - 1)
        f = fwd[idx, v.track]
        f = f / np.maximum(np.linalg.norm(f, axis=1, keepdims=True), 1e-12)
        to_listener = -rel / np.maximum(np.linalg.norm(rel, axis=1, keepdims=True), 1e-12)
        return filters.cone_gain(np.einsum("ni,ni->n", f, to_listener), prm["cone_inner_deg"],
                                 prm["cone_outer_deg"], prm["cone_outer_gain_db"])

    def _follow(self, v: Voice, vis: np.ndarray) -> np.ndarray:
        """Visibility (n, bands) smoothed with the occlusion attack and release, state carried."""
        dt = self.grid.step / self.grid.rate
        down, up = math.exp(-dt / filters.OCCLUSION_ATTACK_S), math.exp(-dt / filters.OCCLUSION_RELEASE_S)
        prev = vis[0] if v.follow is None else v.follow
        out = np.empty_like(vis)
        for band in range(vis.shape[1]):
            x = np.concatenate([[prev[band]], vis[:, band]])
            out[:, band] = kernels.follow(np.ascontiguousarray(x), down, up, np.empty(len(x)))[1:]
        v.follow = out[-1].copy()
        return out

    def render(self, parts: list[Part], c0: int, c1: int, spans, pool) -> tuple[dict, dict, dict]:
        """The far voices' contributions over output samples [c0, c1): per group stereo (n, 2) and
        mono send (n,), and per voice the peak per control point (for the report)."""
        if not parts:
            return {}, {}, {}
        grid = self.grid
        j0 = grid.index_of(c0)
        j1 = min(grid.index_of(c1 - 1) + 1, grid.count - 1)
        n = c1 - c0
        groups: dict[str, list[Part]] = {}
        for pt in parts:
            groups.setdefault(self.voices[pt.voice].group, []).append(pt)
        for g, _ in list(self.states):  # filter tails still ringing in a group without far voices now
            groups.setdefault(g, [])
        # a fixed number of tasks per group, independent of the worker count: each task keeps its own
        # bus filter states (the filters are linear, so filtering per task equals filtering the sum)
        tasks = [(g, t, members[t::TASKS]) for g, members in groups.items() for t in range(TASKS)]

        occ = np.full((n, 1), self.occ_gain)

        def task(item):
            g, t, members = item
            states = self.states.setdefault((g, t), {
                "air": np.zeros((2 * N_BANDS, 2, filters.AIR_SECTIONS, 2)),  # per bus and channel
                "occ": np.zeros((N_BANDS, 2, 1)),  # the occluded buses' low-pass
                "send": np.zeros((N_BANDS, filters.AIR_SECTIONS, 2))})
            if not members and not any(np.any(st) for st in states.values()):
                return g, None, None, {}
            buses = np.zeros((2 * N_BANDS, n, 2))
            sends = np.zeros((N_BANDS, n))
            peaks = {}
            for a in range(0, len(members), BATCH):
                batch = members[a:a + BATCH]
                e, gl, gr, gs, lo, w, fr, sounds = self._control([pt.voice for pt in batch], batch, j0, j1, c0, c1,
                                                                 spans)
                if not sounds.any():
                    continue
                rows = np.nonzero(sounds)[0]
                ids = np.array([batch[r].voice for r in rows], dtype=np.int64)
                pk = np.zeros((len(rows), e.shape[1]))
                kernels.far_mix(self.bufcat, self.v_start[ids], self.v_len[ids], self.v_period[ids],
                                self.v_offset[ids], self.v_origin[ids], self.v_pitch[ids], self.v_phase[ids],
                                e[rows], gl[rows], gr[rows], gs[rows], lo[rows], w[rows], fr[rows], N_BANDS,
                                int(grid.samples[j0]), grid.step, c0, MIX_BLOCK, buses, sends, pk)
                for r, vi in enumerate(ids):
                    peaks[int(vi)] = pk[r]
            y = np.zeros((n, 2))
            for b in range(2 * N_BANDS):
                band, occluded = b % N_BANDS, b >= N_BANDS
                ringing = np.any(states["air"][b]) or occluded and np.any(states["occ"][band])
                if not np.any(buses[b]) and not ringing:
                    continue
                air = self.bus_air[band]
                for ch in (0, 1):
                    x = np.ascontiguousarray(buses[b, :, ch])
                    if air is not None:
                        x = kernels.svf_cascade(x, air, states["air"][b, ch], np.empty(n))
                    if occluded:
                        x = kernels.onepole_cascade(x, occ, states["occ"][band, ch], np.empty(n))
                    y[:, ch] += x
            send = np.zeros(n)
            for band in range(N_BANDS):
                if not np.any(sends[band]) and not np.any(states["send"][band]):
                    continue
                air = self.bus_air[band]
                send += sends[band] if air is None else kernels.svf_cascade(
                    np.ascontiguousarray(sends[band]), air, states["send"][band], np.empty(n))
            return g, y, send, peaks

        mixed, sends, peaks = {}, {}, {}
        for g, y, send, pk in pool.map(task, tasks):  # in task order: deterministic
            peaks.update(pk)
            if y is None:
                continue
            if g in mixed:
                mixed[g] += y
                sends[g] += send
            else:
                mixed[g], sends[g] = y, send
        return mixed, sends, peaks
