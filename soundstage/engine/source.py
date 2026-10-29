"""Per-source rendering: the processing chain of ADR 0009 for one source or voice.

``SpatialRenderer``: emission side (dry timeline at the emission rate, pre-emphasis for the
interpolator, air absorption and rear low-pass) feeding a delay line; reception side (per-ear read
delays, fractional-delay read, ear stages, gains and pan). At jumps (cuts, teleports) a branch
with every parameter held at its value before the jump is read as well and crossfaded out over
10 ms. ``BedRenderer``: non-spatial sources, gain and fades only. Both render output samples
``[a, b)`` chunk by chunk, keep their state in between, and return the stereo contribution and the
mono reverb send (None without a reverb or for beds without ``reverb_send_db``). A spatial renderer
asked to continue after a gap (a chunk skipped by culling) restarts its delay line and filters with
a warm-up; ``power`` estimates the output power per control point for culling.

``make_renderers`` turns a source into one renderer, or one per trigger for one-shots whose
triggers need their own reference delay (``sync_to_picture`` or a Doppler factor other than 1).

Spec: docs/spec/signal-model.md (processing chain, propagation, cuts).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from soundstage.engine import filters, propagation, signals
from soundstage.engine.control import ControlGrid
from soundstage.engine.geometry import Path, SceneGeometry
from soundstage.engine.scene import Scene, Source

CROSSFADE_S = 0.010
PRODUCE_BLOCK_S = 0.5
WARMUP_S = 0.05
FILTER_STEP = 16
"""Control points between evaluations of the filter responses in ``SpatialRenderer.power``."""


@dataclass
class RenderContext:
    """What every renderer of one render shares."""

    scene: Scene
    grid: ControlGrid
    geometry: SceneGeometry
    interp: propagation.Interpolator
    panner: object
    rate: int
    room_rolloff: float | None = None  # reverb send's distance rolloff; None: no reverb in this render
    output_start: int | None = None  # first output sample; the grid may start earlier (reverb pre-roll)

    @property
    def emission_rate(self) -> int:
        return self.rate * self.interp.oversample


class BedRenderer:
    def __init__(self, ctx: RenderContext, source: Source, sample: np.ndarray):
        p = source.params
        scene, rate = ctx.scene, ctx.rate
        start = None if p["frame"] is None else (
            [scene.sample_of(f) for f in p["frame"]] if isinstance(p["frame"], list) else scene.sample_of(p["frame"]))
        end = scene.sample_of(p["end_frame"]) if p["end_frame"] is not None else None
        self.source, self.grid = source, ctx.grid
        self.dry = signals.DryGenerator(sample, p, rate, start, end, source.id)
        self.gain = float(filters.db_to_gain(p["gain_db"]))
        self.send = None
        if ctx.room_rolloff is not None and p["reverb_send_db"] is not None:
            self.send = self.gain * float(filters.db_to_gain(p["reverb_send_db"] + ctx.scene.settings["reverb_send_db"]))
        self.info: dict = {}

    def render(self, a: int, b: int) -> tuple[np.ndarray, np.ndarray | None]:
        dry = self.dry.window(a, b)
        return dry * self.gain, (dry.mean(axis=1) * self.send if self.send is not None else None)

    def power(self) -> np.ndarray:
        """Estimated output power per control point (both channels and the send), for culling."""
        g = self.grid
        a = g.samples - g.step // 2
        return (self.gain ** 2 + (self.send or 0.0) ** 2) * self.dry.energy(a, a + g.step) / g.step


class _Branch:
    """Held parameters of the segment before a jump, read until its crossfade has ended."""

    def __init__(self, start: int, index: int, r: SpatialRenderer):
        self.start, self.end = start, start + r.crossfade
        d = r.delays
        self.tau_l, self.tau_r = float(d.left[index]), float(d.right[index])
        self.gain_l, self.gain_r = float(r.gain_l[index]), float(r.gain_r[index])
        self.ear_l = [st.held(index) for st in r.ear_l]
        self.ear_r = [st.held(index) for st in r.ear_r]
        self.tau_c = float(d.centre[index])
        self.send = float(r.send[index]) if r.send is not None else None

    def render(self, r: SpatialRenderer, a: int, b: int) -> tuple[np.ndarray, np.ndarray | None]:
        t = np.arange(a, b) / r.rate
        ones = np.ones(b - a)
        yl = r.line.read(r.interp, (t - self.tau_l) * r.fe, ones)
        yr = r.line.read(r.interp, (t - self.tau_r) * r.fe, ones)
        for st in self.ear_l:
            yl = st.process(yl, a, b)
        for st in self.ear_r:
            yr = st.process(yr, a, b)
        send = None
        if self.send is not None:
            send = r.line.read(r.interp, (t - self.tau_c) * r.fe, ones) * self.send
        return np.stack([yl * self.gain_l, yr * self.gain_r], axis=1), send

    def position(self, r: SpatialRenderer, n: int) -> float:
        return (n / r.rate - max(self.tau_l, self.tau_r)) * r.fe


class SpatialRenderer:
    def __init__(self, ctx: RenderContext, source: Source, params: dict, path: Path, sample: np.ndarray,
                 voice: str = ""):
        scene, s, grid = ctx.scene, ctx.scene.settings, ctx.grid
        self.source, self.params, self.path, self.voice = source, params, path, voice
        self.grid, self.rate, self.interp = grid, ctx.rate, ctx.interp
        self.output_start = ctx.output_start
        self.fe = ctx.emission_rate
        self.crossfade = int(round(CROSSFADE_S * ctx.rate))
        p = params

        # read delays
        k = s["doppler_factor"] * p["doppler"]
        sync = bool(p["sync_to_picture"]) and p["mode"] == "once"
        tau0 = self._reference_delay(ctx)
        self.delays = propagation.read_delays(path.tau, grid.step / grid.rate, path.jumps, k=k, tau0=tau0, sync=sync,
                                              itd=ctx.panner.itd(path), audible=path.audible)

        # gains on the control grid
        g = float(filters.db_to_gain(p["gain_db"])) * filters.distance_gain(
            path.distance, p["distance_model"], p["ref_distance"], p["max_distance"], p["rolloff"])
        g = g * filters.cone_gain(path.cos_emit, p["cone_inner_deg"], p["cone_outer_deg"], p["cone_outer_gain_db"])
        if ctx.panner.rear_cue:
            g = g * filters.rear_gain(path.rear, s["rear_gain_db"])
        g = g * path.audible
        occ_gain, occ_cutoff = None, None
        if p["occlusion"] and path.visibility is not None:
            occ_gain, occ_cutoff = filters.occlusion_filter(path.visibility, scene.visibility_bands,
                                                            s["occlusion_gain_db"], s["occlusion_cutoff_hz"],
                                                            grid.step / grid.rate)
            g = g * occ_gain
        self.visibility = path.visibility
        gl, gr = ctx.panner.gains(path)
        self.gain_l, self.gain_r = g * gl, g * gr

        # reverb send: the distance law with the environment's room rolloff (EFX), no pan or ear cues
        self.send = None
        if ctx.room_rolloff is not None:
            send_db = (p["reverb_send_db"] or 0.0) + s["reverb_send_db"]
            self.send = (float(filters.db_to_gain(p["gain_db"] + send_db)) * path.audible
                         * filters.distance_gain(path.distance, p["distance_model"], p["ref_distance"],
                                                 p["max_distance"], ctx.room_rolloff)
                         * filters.cone_gain(path.cos_emit, p["cone_inner_deg"], p["cone_outer_deg"],
                                             p["cone_outer_gain_db"]))
            if occ_gain is not None and p["occlusion_mode"] == "occlusion":
                self.send = self.send * occ_gain

        # emission side: parameters on emission time
        te = np.maximum.accumulate(grid.times - self.delays.centre)
        air = filters.AirAbsorption(s["air_temperature_c"], s["air_humidity_pct"], self.fe,
                                    scale=s["air_absorption"] * p["air_absorption"])
        self.emission_stages = [filters.OnePoleStage(te, air.cutoffs(path.distance), self.fe)]
        if ctx.panner.rear_cue:
            self.emission_stages.append(filters.RearStage(te, path.rear, s["rear_cutoff_hz"], self.fe))
        self.ear_l, self.ear_r = ctx.panner.ear_stages(path, ctx.rate)
        self.send_stages = []
        if occ_cutoff is not None and np.isfinite(occ_cutoff).any():
            self.ear_l = [filters.GridOnePoleStage(grid, occ_cutoff, ctx.rate, path.jumps)] + self.ear_l
            self.ear_r = [filters.GridOnePoleStage(grid, occ_cutoff, ctx.rate, path.jumps)] + self.ear_r
            if p["occlusion_mode"] == "occlusion" and self.send is not None:
                self.send_stages = [filters.GridOnePoleStage(grid, occ_cutoff, ctx.rate, path.jumps)]

        f = p["frame"]
        start = None if f is None else ([self._emission_index(x, scene) for x in f] if isinstance(f, list)
                                        else self._emission_index(f, scene))
        end = self._emission_index(p["end_frame"], scene) if p["end_frame"] is not None else None
        prefilter = ctx.interp.prefilter() if ctx.interp.prefilter else None
        self.dry = signals.DryGenerator(sample, p, self.fe, start, end, source.id, prefilter)

        # delay line: keep every emission sample a future read may need (a cut can jump back)
        need = (grid.times - np.maximum(self.delays.left, self.delays.right)) * self.fe
        self.keep = np.minimum.accumulate(need[::-1])[::-1]
        first = int(math.floor(self.keep[0])) - ctx.interp.halfwidth - int(WARMUP_S * self.fe)
        self.line = propagation.DelayLine(self._produce, first, int(PRODUCE_BLOCK_S * self.fe))
        self.jump_starts = {int(grid.samples[j - 1]): int(j - 1) for j in path.jumps if j >= 1}
        self.branches: list[_Branch] = []
        self.next: int | None = None  # output sample where the state continues (None: fresh)
        self.info = self._info(scene)

    def _emission_index(self, frame: float, scene: Scene) -> int:
        return int(round(scene.seconds(frame) * self.fe))

    def _reference_delay(self, ctx: RenderContext) -> float:
        """tau0: delay heard at the reception of the trigger / loop start (or at the shot start)."""
        p, geo, track = self.params, ctx.geometry, self.source.track
        f = p["frame"][0] if isinstance(p["frame"], list) else p["frame"]
        if f is None:
            return geo.delay_at(track, 0.0)
        t_emit = float(ctx.scene.seconds(f))
        t = t_emit
        for _ in range(6):  # reception time t with t - tau(t) = t_emit
            t = t_emit + geo.delay_at(track, t)
        return geo.delay_at(track, t)

    def _produce(self, a: int, b: int) -> np.ndarray:
        x = self.dry.window(a, b)
        for st in self.emission_stages:
            x = st.process(x, a, b)
        return x

    def _main(self, a: int, b: int) -> np.ndarray:
        g, d, jumps = self.grid, self.delays, self.path.jumps
        t = np.arange(a, b) / self.rate
        rate = g.linear(d.rate, a, b, jumps)
        yl = self.line.read(self.interp, (t - g.cubic(d.left, a, b, jumps)) * self.fe, rate)
        yr = self.line.read(self.interp, (t - g.cubic(d.right, a, b, jumps)) * self.fe, rate)
        for st in self.ear_l:
            yl = st.process(yl, a, b)
        for st in self.ear_r:
            yr = st.process(yr, a, b)
        out = np.stack([yl * g.linear(self.gain_l, a, b, jumps), yr * g.linear(self.gain_r, a, b, jumps)], axis=1)
        send = None
        if self.send is not None:
            yc = self.line.read(self.interp, (t - g.cubic(d.centre, a, b, jumps)) * self.fe, rate)
            for st in self.send_stages:
                yc = st.process(yc, a, b)
            send = yc * g.linear(self.send, a, b, jumps)
        return out, send

    def power(self) -> np.ndarray:
        """Estimated output power per control point (both ears and the reverb send), for culling:
        the gains times the share of the sample's power each path's filters pass (its band
        spectrum, shifted by the pitch, weighted by their responses every ``FILTER_STEP`` control
        points) times the dry signal's mean square around the emission time; widened by one control
        point (ITD, interpolator support)."""
        te = (self.grid.times - self.delays.centre) * self.fe
        width = np.maximum(np.abs(np.gradient(te)), 1.0) if len(te) > 1 else np.ones(len(te))
        a = np.floor(te - width / 2).astype(np.int64)
        b = a + np.maximum(np.ceil(width).astype(np.int64), 1)
        n = len(te)
        idx = np.unique(np.append(np.arange(0, n, FILTER_STEP), n - 1))
        f, w = signals.sample_bands(self.params["sample"])
        f = f * self.params["pitch"]
        common = np.ones((len(idx), len(f)))
        for st in self.emission_stages:
            common *= st.power_response(f, idx)

        def passed(stages) -> np.ndarray:
            r = common.copy()
            for st in stages:
                r *= st.power_response(f, idx)
            return np.interp(np.arange(n), idx, r @ w)

        g2 = self.gain_l ** 2 * passed(self.ear_l) + self.gain_r ** 2 * passed(self.ear_r)
        if self.send is not None:
            g2 = g2 + self.send ** 2 * passed(self.send_stages)
        p = g2 * self.dry.energy(a, b) / (b - a)
        if len(p) > 2:
            p = np.maximum(p, np.maximum(np.concatenate([p[1:], p[-1:]]), np.concatenate([p[:1], p[:-1]])))
        return p

    def _restart(self, a: int) -> None:
        """Continue at output sample ``a`` after a gap (culling): a new delay line and cleared filter
        states, warmed up over ``WARMUP_S`` of output before ``a``."""
        s = max(a - int(WARMUP_S * self.rate), self.grid.start)
        first = int(math.floor(self.keep[self.grid.index_of(s)])) - self.interp.halfwidth - int(WARMUP_S * self.fe)
        self.line = propagation.DelayLine(self._produce, first, int(PRODUCE_BLOCK_S * self.fe))
        for st in (*self.emission_stages, *self.ear_l, *self.ear_r, *self.send_stages):
            st.state[:] = 0.0
        self.branches = []
        self.next = s
        if s < a:
            self.render(s, a)

    def render(self, a: int, b: int) -> tuple[np.ndarray, np.ndarray | None]:
        if a != self.next and (self.next is not None or a - self.grid.start > int(WARMUP_S * self.rate)):
            self._restart(a)
        out = np.empty((b - a, 2))
        send_out = np.empty(b - a) if self.send is not None else None
        cuts = sorted(n for n in self.jump_starts if a < n < b)
        edges = [a, *cuts, b]
        for u, v in zip(edges[:-1], edges[1:]):
            if u in self.jump_starts:
                self.branches.append(_Branch(u, self.jump_starts[u], self))
            y, ys = self._main(u, v)
            for br in self.branches:
                o0, o1 = max(u, br.start), min(v, br.end)
                if o0 >= o1:
                    continue
                w = (np.arange(o0, o1) - br.start + 0.5) / self.crossfade * (np.pi / 2)
                held, held_send = br.render(self, o0, o1)
                y[o0 - u:o1 - u] = y[o0 - u:o1 - u] * np.sin(w)[:, None] + held * np.cos(w)[:, None]
                if ys is not None:
                    ys[o0 - u:o1 - u] = ys[o0 - u:o1 - u] * np.sin(w) + held_send * np.cos(w)
            out[u - a:v - a] = y
            if send_out is not None:
                send_out[u - a:v - a] = ys
        self.branches = [br for br in self.branches if br.end > b]
        keep = self.keep[min(self.grid.index_of(b), len(self.keep) - 1)]
        for br in self.branches:
            keep = min(keep, br.position(self, b))
        self.line.trim(int(math.floor(keep)) - self.interp.halfwidth - 2)
        self.next = b
        return out, send_out

    def _info(self, scene: Scene) -> dict:
        g, path, d = self.grid, self.path, self.delays
        first = g.start + 3 * g.step if self.output_start is None else self.output_start
        inside = (g.samples >= first) & (g.samples <= g.samples[-1] - 3 * g.step)
        settle = np.ones(len(d.rate), dtype=bool)
        for j in path.jumps:
            settle[max(j - 2, 0):j + 2] = False
        sel = inside & settle & path.audible
        # per-frame tracks for the debug plot (control points nearest to each frame start)
        frames = np.arange(scene.frame_start, scene.frame_end + 1)
        idx = np.clip(((frames - scene.frame_start) / scene.fps * g.rate - g.start) // g.step, 0, g.count - 1).astype(int)
        level = np.sqrt(self.gain_l ** 2 + self.gain_r ** 2)
        track = {
            "frame": frames.astype(float),
            "distance_m": path.distance[idx],
            "level_db": 20 * np.log10(np.maximum(level[idx], 1e-6)),
            "pan": path.lateral[idx],
            "delay_ms": d.centre[idx] * 1e3,
            "rate": d.rate[idx],
        }
        if self.visibility is not None and self.params["occlusion"]:
            track["visibility"] = self.visibility[idx].mean(axis=1)
        return {
            "distance": path.distance[inside],
            "rate": d.rate[sel] if sel.any() else d.rate[inside],
            "delay": d.centre[inside],
            "clamped": d.clamped,
            "before_bake": int(np.sum(path.before_bake & (g.samples >= first))) if path.before_bake is not None else 0,
            "jumps": len(path.jumps),
            "track": track,
        }


def _voices(source: Source, k: float) -> list[tuple[dict, str]]:
    p = source.params
    triggers = p["frame"] if isinstance(p["frame"], list) else None
    if p["mode"] == "once" and triggers and len(triggers) > 1 and (p["sync_to_picture"] or k != 1.0):
        return [({**p, "frame": t}, f"#{i}") for i, t in enumerate(triggers)]
    return [(p, "")]


def make_renderers(ctx: RenderContext, source: Source, sample: np.ndarray) -> list:
    """Renderers for one source (several voices for one-shots that need per-trigger references)."""
    if not source.spatial:
        return [BedRenderer(ctx, source, sample)]
    path = ctx.geometry.path(source.track)
    k = ctx.scene.settings["doppler_factor"] * source.params["doppler"]
    return [SpatialRenderer(ctx, source, params, path, sample, voice) for params, voice in _voices(source, k)]
