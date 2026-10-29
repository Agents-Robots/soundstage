"""Render orchestration: scene in, stereo buffer and statistics out.

Builds the shared context (control grid, scene geometry, interpolator, panner, reverb environment)
and one renderer per source or voice (``engine/source.py``), then renders the output window in
chunks (4 s). Within a chunk the renderers run in a thread pool (numba kernels release the GIL);
contributions are summed in source order, so the output is bit-identical between runs (NFR-2, ADR
0009). Sources feed their group's bus (stems) and a mono reverb send; the summed send is convolved
once per chunk and the reverb return is its own stem. Stems sum to the master.

Supports frame sub-ranges and solo/mute (FR-67). Data flow: docs/architecture.md#data-flow-inside-a-render.
"""

from __future__ import annotations

import fnmatch
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np

from soundstage.blender import schema
from soundstage.engine import cull, filters, kernels, panning, propagation, reverb, signals
from soundstage.engine.control import CONTROL_STEP, ControlGrid
from soundstage.engine.geometry import SceneGeometry
from soundstage.engine.scene import Scene, Source
from soundstage.engine.source import RenderContext, make_renderers

CHUNK_BLOCKS = 4_000
"""Control blocks per chunk (4 s at 48 kHz)."""

AUDIBLE_DBFS = -60.0
CULL_FADE_S = 0.010
"""Fade into and out of a chunk skipped by culling, rendered inside the skipped chunk."""


@dataclass
class RenderResult:
    audio: np.ndarray  # (n, 2) float64
    rate: int
    frames: tuple[int, int]
    sources: list[dict]
    warnings: list[str] = field(default_factory=list)
    timing_s: dict = field(default_factory=dict)
    stems: dict[str, np.ndarray] = field(default_factory=dict)  # group -> (n, 2), and "reverb"
    reverb: str | None = None
    culling: dict | None = None  # summary when cull_db is set


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
           mute: list[str] = (), workers: int | None = None, stems: bool = False) -> RenderResult:
    t_start = time.perf_counter()
    rate = scene.sample_rate
    s = scene.settings
    fa, fb = frames or (scene.frame_start, scene.frame_end)
    n0 = scene.sample_of(fa)
    n1 = n0 + scene.length_samples(fa, fb)
    step = CONTROL_STEP
    warnings = list(scene.warnings)
    for key in schema.unimplemented(scene.manifest.get("settings", {}), schema.SCENE_SETTINGS):
        warnings.append(f"setting {key!r} is not implemented yet, ignored")
    if s["pan_reference"] == "screen":
        frame = scene.listener_frame
        if frame is None:
            warnings.append("pan_reference 'screen': the scene file has no frame edges (baked before scene "
                            "format 2, or made without a camera), panning follows the camera")
        elif not np.isfinite(frame).all():
            warnings.append("pan_reference 'screen': the listener is not a perspective camera at some baked "
                            "samples, panning follows the camera there")

    selected = select(scene.sources, list(solo), list(mute))
    if scene.sources and not selected:
        warnings.append("no source selected (--solo/--mute): the render is silent")
    interp = propagation.interpolator_for(s["quality"])
    env = reverb.environment(s["reverb"], rate, s["reverb_room_rolloff"]) if s["reverb"] else None
    if env is not None and stems and any(src.group == "reverb" for src in selected):
        warnings.append("group 'reverb' shares its stem with the reverb return")
    chunk = CHUNK_BLOCKS * step
    chunks = [(c0, min(c0 + chunk, n1)) for c0 in range(n0, n1, chunk)]
    cull_db = s["cull_db"]
    t_cull = 0.0
    active, skipped = selected, []  # skipped: culled before setup
    spans = cull.blocks(chunks, int(round(cull.BLOCK_S * rate)))
    if cull_db is not None and selected and chunks:
        t0 = time.perf_counter()
        before = cull.before_setup(scene, selected, spans, cull_db, env.room_rolloff if env else None)
        active = [src for src, k in zip(selected, before) if not k]
        skipped = [src for src, k in zip(selected, before) if k]
        t_cull += time.perf_counter() - t0
    # reverb pre-roll: render the sends for up to one impulse-response length before the first output
    # sample (within the baked padding), so sound already playing at the start has its reverberation
    pre = 0 if env is None else max(0, min(len(env.ir), n0 - scene.sample_of(float(scene.frames[0]))))
    r0 = n0 - pre
    grid = ControlGrid.covering(r0, n1, rate)
    ctx = RenderContext(scene=scene, grid=grid, geometry=SceneGeometry(scene, grid), interp=interp,
                        panner=panning.PANNERS[s["panner"]](s), rate=rate,
                        room_rolloff=env.room_rolloff if env else None, output_start=n0)
    kernels.warmup()
    filters.AirAbsorption(s["air_temperature_c"], s["air_humidity_pct"], ctx.emission_rate)  # fit once, cached
    n_workers = max(1, min(workers or os.cpu_count() or 1, len(active)))

    def build(src: Source) -> tuple[list, float]:
        sample_rate = ctx.emission_rate if src.spatial else rate
        sample = signals.load_sample(src.params["sample"], sample_rate, pitch=src.params["pitch"],
                                     stereo=not src.spatial)
        return make_renderers(ctx, src, sample), len(sample) * rate / sample_rate

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        built = list(pool.map(build, active))
    voices = [b[0] for b in built]
    sample_len = {src.id: b[1] for src, b in zip(active, built)}
    for src in active:
        for key in schema.unimplemented(src.params, schema.SOURCE_KEYS):
            warnings.append(f"{src.id}: {key!r} is not implemented yet, ignored")

    # culling plan: per source, (voices, chunks) True where a voice renders; None: everything renders
    keep: list[np.ndarray] | None = None
    if cull_db is not None and active and chunks:
        t0 = time.perf_counter()
        flat = [(i, r) for i, v in enumerate(voices) for r in v]
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            power = list(pool.map(lambda ir: ir[1].power(), flat))
        mask = cull.plan(power, [active[i].group for i, _ in flat], [active[i].spatial for i, _ in flat],
                         grid, spans, len(chunks), cull_db)
        rows = np.cumsum([0] + [len(v) for v in voices])
        keep = [mask[rows[i]:rows[i + 1]] for i in range(len(active))]
        t_cull += time.perf_counter() - t0
    t_loaded = time.perf_counter()

    master = np.zeros((n1 - n0, 2))
    groups = list(dict.fromkeys(src.group for src in selected))
    buses = {g: np.zeros((n1 - n0, 2), np.float32) for g in groups} if stems else {}
    bus = reverb.ReverbBus(env) if env else None
    if bus is not None and stems:
        buses["reverb"] = np.zeros((n1 - n0, 2), np.float32)
    n_blocks = -(-(n1 - n0) // step)
    block_peak = [np.zeros(n_blocks) for _ in active]
    fade = int(round(CULL_FADE_S * rate))

    def voice_part(r, plan: np.ndarray | None, ci: int | None, c0: int, c1: int):
        """One voice over [c0, c1) (chunk ci; None: reverb pre-roll) under the culling plan: the
        whole chunk, or only the fades into and out of a skipped chunk, or nothing (None, None)."""
        if plan is None or plan[0 if ci is None else ci]:
            return r.render(c0, c1)
        if ci is None:
            return None, None
        before = ci > 0 and plan[ci - 1]
        after = ci + 1 < len(plan) and plan[ci + 1]
        if not (before or after):
            return None, None
        f = min(fade, (c1 - c0) // 2)
        if not f:
            return None, None
        up = signals.raised_cosine(f)
        out, send = np.zeros((c1 - c0, 2)), None
        for at, gain, wanted in ((c0, up[::-1], before), (c1 - f, up, after)):
            if not wanted:
                continue
            y, sd = r.render(at, at + f)  # fading in restarts the voice (warm-up) before at
            out[at - c0: at - c0 + f] += y * gain[:, None]
            if sd is not None:
                send = np.zeros(c1 - c0) if send is None else send
                send[at - c0: at - c0 + f] += sd * gain
        return out, send

    def voice_chunk(i: int, ci: int | None, c0: int, c1: int) -> tuple[np.ndarray | None, np.ndarray | None]:
        """All voices of source i over [c0, c1), and its send (None where nothing was rendered)."""
        contrib, send = None, None
        for k, r in enumerate(voices[i]):
            c, sd = voice_part(r, keep[i][k] if keep is not None else None, ci, c0, c1)
            if c is None:
                continue
            contrib = c if contrib is None else contrib + c
            send = sd if send is None else (send if sd is None else send + sd)
        return contrib, send

    def source_chunk(i: int, ci: int, c0: int, c1: int) -> tuple[np.ndarray | None, np.ndarray | None]:
        """All voices of source i over [c0, c1), its send, and its 1 ms block peaks (in the worker)."""
        contrib, send = voice_chunk(i, ci, c0, c1)
        if contrib is not None:
            b0 = (c0 - n0) // step
            starts = np.arange(0, c1 - c0, step)
            block_peak[i][b0: b0 + len(starts)] = np.maximum.reduceat(np.abs(contrib).max(axis=1), starts)
        return contrib, send

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        for c0 in range(r0, n0, chunk):  # pre-roll: only the reverb bus keeps what it gets
            c1 = min(c0 + chunk, n0)
            sends = [sd for _, sd in pool.map(lambda i: voice_chunk(i, None, c0, c1), range(len(active)))]
            bus.process(sum((sd for sd in sends if sd is not None), np.zeros(c1 - c0)))
        for ci, (c0, c1) in enumerate(chunks):
            send_sum = np.zeros(c1 - c0)
            for i, (contrib, send) in enumerate(pool.map(lambda i: source_chunk(i, ci, c0, c1), range(len(active)))):
                if contrib is not None:
                    master[c0 - n0: c1 - n0] += contrib  # in source order: deterministic
                    if stems:
                        buses[active[i].group][c0 - n0: c1 - n0] += contrib
                if send is not None:
                    send_sum += send
            if bus is not None:
                wet = bus.process(send_sum)
                master[c0 - n0: c1 - n0] += wet
                if stems:
                    buses["reverb"][c0 - n0: c1 - n0] += wet
    master_gain = float(filters.db_to_gain(s["master_gain_db"]))
    master *= master_gain
    for b in buses.values():
        b *= master_gain
    t_dsp = time.perf_counter()

    # Block index of each frame boundary, for per-frame audibility.
    frame_blocks = [(scene.sample_of(f) - n0) // step for f in range(fa, fb + 2)]
    infos = {i: [r.info for r in v] for i, v in enumerate(voices)}
    before_bake: list[tuple[float, str]] = []
    stats: dict[str, dict] = {}
    fb_lo = np.clip(np.array(frame_blocks[:-1]), 0, n_blocks - 1)
    fb_ok = np.array(frame_blocks[1:]) > np.array(frame_blocks[:-1])
    threshold = float(filters.db_to_gain(AUDIBLE_DBFS))
    chunk_s = np.array([(c1 - c0) / rate for c0, c1 in chunks])
    total_s = (n1 - n0) / rate
    culled_whole = 0
    for i, src in enumerate(active):
        bp = block_peak[i] * master_gain  # the source's peaks as they are in the output
        frame_peak = np.maximum.reduceat(bp, fb_lo) if len(bp) else np.zeros(0)
        audible = int(np.sum((frame_peak > threshold) & fb_ok)) if len(bp) else 0
        st = {
            "id": src.id,
            "group": src.group,
            "sample": os.path.basename(src.params["sample"]),
            "mode": src.params["mode"],
            "spatial": src.spatial,
            "active_frames": _active_frames(src, sample_len[src.id], scene, fa, fb),
            "peak_dbfs": round(float(filters.gain_to_db(bp.max() if len(bp) else 0.0)), 2),
            "audible_frames": audible,
        }
        whole = False
        if keep is not None:
            culled = float(np.sum(chunk_s[~keep[i].any(axis=0)]))
            st["culled_s"] = round(culled, 2)
            whole = culled >= total_s - 1e-9
            culled_whole += whole
        if src.spatial:
            info = infos[i]
            dist = np.concatenate([x["distance"] for x in info])
            rates = np.concatenate([x["rate"] for x in info])
            delay = np.concatenate([x["delay"] for x in info])
            st["distance_m"] = [round(float(dist.min()), 2), round(float(dist.max()), 2)]
            st["delay_ms"] = [round(float(delay.min()) * 1e3, 1), round(float(delay.max()) * 1e3, 1)]
            st["rate"] = [round(float(rates.min()), 4), round(float(rates.max()), 4)]
            clamped = max(x["clamped"] for x in info)
            if clamped:
                warnings.append(f"{src.id}: playback rate clamped to [{propagation.RATE_MIN:g}, "
                                f"{propagation.RATE_MAX:g}] for {clamped * step / rate:.2f} s "
                                "(near- or supersonic motion)")
            early = max(x["before_bake"] for x in info) * step / rate
            if early:
                before_bake.append((early, src.id))
        if src.spatial:
            st["_track"] = infos[i][0].get("track")  # for the debug plot; dropped from the report
            if st["_track"] is not None and "visibility" in st["_track"]:
                tr = st["_track"]
                v = tr["visibility"][(tr["frame"] >= fa) & (tr["frame"] <= fb)]
                if len(v):
                    st["visibility"] = [round(float(v.min()), 2), round(float(v.max()), 2)]
                    st["occluded_frames"] = int(np.sum(v < 0.5))
        stats[src.id] = st
        if audible == 0 and not whole:
            warnings.append(f"{src.id}: never audible (peak below {AUDIBLE_DBFS:g} dBFS in every frame)")
    for src in skipped:
        length = signals.sample_stats(src.params["sample"])[2] * rate / src.params["pitch"]
        stats[src.id] = {"id": src.id, "group": src.group, "sample": os.path.basename(src.params["sample"]),
                         "mode": src.params["mode"], "spatial": src.spatial,
                         "active_frames": _active_frames(src, length, scene, fa, fb),
                         "peak_dbfs": round(float(filters.gain_to_db(0.0)), 2), "audible_frames": 0,
                         "culled_s": round(total_s, 2)}
    if before_bake:
        worst, worst_id = max(before_bake)
        warnings.append(f"{len(before_bake)} source(s) need positions from before the baked range (up to "
                        f"{worst:.2f} s, {worst_id}); positions are held there. Re-bake with --pad "
                        f"{math.ceil(worst * 10) / 10:g} for exact delays and Doppler at the start")
    culling = None
    if cull_db is not None:
        n_voices = sum(len(v) for v in voices) + len(skipped)
        rendered = sum(int(k.sum()) for k in keep) if keep is not None else 0
        culling = {"cull_db": cull_db, "sources": len(selected), "skipped_before_setup": len(skipped),
                   "skipped_entirely": len(skipped) + culled_whole,
                   "rendered_share": round(rendered / max(n_voices * len(chunks), 1), 4)}
    timing = {"load": round(t_loaded - t_start, 3), "dsp": round(t_dsp - t_loaded, 3), "workers": n_workers}
    if cull_db is not None:
        timing["cull"] = round(t_cull, 3)
    return RenderResult(
        audio=master,
        rate=rate,
        frames=(fa, fb),
        sources=[stats[src.id] for src in selected],
        warnings=warnings,
        timing_s=timing,
        stems=buses,
        reverb=env.name if env else None,
        culling=culling,
    )
