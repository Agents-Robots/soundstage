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
from soundstage.engine import cull, farfield, filters, kernels, panning, propagation, reverb, signals
from soundstage.engine.control import CONTROL_STEP, ControlGrid
from soundstage.engine.geometry import SceneGeometry
from soundstage.engine.scene import Scene, Source
from soundstage.engine.source import WARMUP_S, RenderContext, make_renderers
from soundstage.levels import skip_mask

CHUNK_BLOCKS = 4_000
"""Control blocks per chunk (4 s at 48 kHz)."""

AUDIBLE_DBFS = -60.0
OVERLOAD_GAIN = 10.0
"""A master peak above this (+20 dBFS) is reported: no mix wants it, a diverging render shows here."""
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
    lod: dict | None = None  # summary when some source was rendered in the far field (detail_voices)


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
    baked = scene.manifest.get("settings", {}).get("detail_voices")
    if (scene.manifest.get("occlusion") or {}).get("direct_share") and (
            s["detail_voices"] is None or s["detail_voices"] > baked):
        warnings.append(f"visibility was baked from the direct path alone for sources beyond 2 x detail_voices "
                        f"{baked} per group; with detail_voices {s['detail_voices']} some near sources get it: "
                        f"bake with the same detail_voices for every path")

    selected = select(scene.sources, list(solo), list(mute))
    if scene.sources and not selected:
        warnings.append("no source selected (--solo/--mute): the render is silent")
    interp = propagation.interpolator_for(s["quality"])
    env = reverb.environment(s["reverb"], rate, s["reverb_room_rolloff"]) if s["reverb"] else None
    if env is not None and stems and any(src.group == "reverb" for src in selected):
        warnings.append("group 'reverb' shares its stem with the reverb return")
    chunk = CHUNK_BLOCKS * step
    chunks = [(c0, min(c0 + chunk, n1)) for c0 in range(n0, n1, chunk)]
    cull_db, detail = s["cull_db"], s["detail_voices"]
    send_law = reverb.send_law(env, s["reverb_send_law"], s["reverb_radius_m"], float(s["speed_of_sound"]))
    t_cull = 0.0
    active, skipped = selected, []  # skipped: culled before setup
    spans = cull.blocks(chunks, int(round(cull.BLOCK_S * rate)))
    levels = None  # (bound, estimate) per source and decision block, from the baked positions
    if (cull_db is not None or detail is not None) and selected and chunks:
        t0 = time.perf_counter()
        levels = cull.estimates(scene, selected, spans, send_law)
        if cull_db is not None:
            before = cull.before_setup(scene, selected, spans, cull_db, send_law, levels)
            active = [src for src, k in zip(selected, before) if not k]
            skipped = [src for src, k in zip(selected, before) if k]
            levels = tuple(x[~before] for x in levels)
        t_cull += time.perf_counter() - t0
    # tiers (FR-56): near (full chain) or far field, per source and chunk; None: every source near
    near = None
    if detail is not None and active and chunks:
        near = farfield.assign_tiers(levels[1], [src.group for src in active],
                                     np.array([src.spatial for src in active]), spans, len(chunks), detail)
        if near.all():
            near = None
    # reverb pre-roll: render the sends for up to one impulse-response length before the first output
    # sample (within the baked padding), so sound already playing at the start has its reverberation
    pre = 0 if env is None else max(0, min(len(env.ir), n0 - scene.sample_of(float(scene.frames[0]))))
    r0 = n0 - pre
    grid = ControlGrid.covering(r0, n1, rate)
    ctx = RenderContext(scene=scene, grid=grid, geometry=SceneGeometry(scene, grid), interp=interp,
                        panner=panning.PANNERS[s["panner"]](s), rate=rate, send=send_law, output_start=n0)
    kernels.warmup()
    filters.AirAbsorption(s["air_temperature_c"], s["air_humidity_pct"], ctx.emission_rate)  # fit once, cached
    n_workers = max(1, min(workers or os.cpu_count() or 1, len(active)))
    for src in active:
        for key in schema.unimplemented(src.params, schema.SOURCE_KEYS):
            warnings.append(f"{src.id}: {key!r} is not implemented yet, ignored")

    def build(src: Source, c: RenderContext = ctx) -> tuple[list, float]:
        sample_rate = c.emission_rate if src.spatial else rate
        sample = signals.load_sample(src.params["sample"], sample_rate, pitch=src.params["pitch"],
                                     stereo=not src.spatial)
        return make_renderers(c, src, sample), len(sample) * rate / sample_rate

    master = np.zeros((n1 - n0, 2))
    groups = list(dict.fromkeys(src.group for src in selected))
    buses = {g: np.zeros((n1 - n0, 2), np.float32) for g in groups} if stems else {}
    bus = reverb.ReverbBus(env) if env else None
    if bus is not None and stems:
        buses["reverb"] = np.zeros((n1 - n0, 2), np.float32)
    n_blocks = -(-(n1 - n0) // step)
    # per source, the peak of each frame of the output (from 1 ms block peaks)
    frame_blocks = [(scene.sample_of(f) - n0) // step for f in range(fa, fb + 2)]
    fb_lo = np.clip(np.array(frame_blocks[:-1]), 0, max(n_blocks - 1, 0))
    block_frame = np.searchsorted(fb_lo, np.arange(n_blocks), side="right") - 1
    frame_peak = np.zeros((len(active), len(fb_lo)))
    fade = int(round(CULL_FADE_S * rate))
    keep: list[np.ndarray] | None = None  # culling plan (voices, chunks) per source; None: everything renders
    infos: dict[int, list[dict]] = {i: [] for i in range(len(active))}
    lod = None

    def note_peaks(i: int, contrib: np.ndarray, c0: int, c1: int) -> None:
        b0 = (c0 - n0) // step
        starts = np.arange(0, c1 - c0, step)
        bp = np.maximum.reduceat(np.abs(contrib).max(axis=1), starts)
        with np.errstate(invalid="ignore"):  # a NaN contribution leaves NaN in the peaks, reported below
            np.maximum.at(frame_peak[i], block_frame[b0: b0 + len(starts)], bp)

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

    def mix_chunk(i: int, contrib, c0: int, c1: int) -> None:
        master[c0 - n0: c1 - n0] += contrib  # in source order: deterministic
        if stems:
            buses[active[i].group][c0 - n0: c1 - n0] += contrib

    if near is None:
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            built = list(pool.map(build, active))
        voices = [b[0] for b in built]
        sample_len = {src.id: b[1] for src, b in zip(active, built)}
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
            """All voices of source i over [c0, c1) and its send; notes its peaks (in the worker)."""
            contrib, send = voice_chunk(i, ci, c0, c1)
            if contrib is not None:
                note_peaks(i, contrib, c0, c1)
            return contrib, send

        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            for c0 in range(r0, n0, chunk):  # pre-roll: only the reverb bus keeps what it gets
                c1 = min(c0 + chunk, n0)
                sends = [sd for _, sd in pool.map(lambda i: voice_chunk(i, None, c0, c1), range(len(active)))]
                bus.process(sum((sd for sd in sends if sd is not None), np.zeros(c1 - c0)))
            for ci, (c0, c1) in enumerate(chunks):
                send_sum = np.zeros(c1 - c0)
                for i, (contrib, send) in enumerate(pool.map(lambda i: source_chunk(i, ci, c0, c1),
                                                             range(len(active)))):
                    if contrib is not None:
                        mix_chunk(i, contrib, c0, c1)
                    if send is not None:
                        send_sum += send
                if bus is not None:
                    wet = bus.process(send_sum)
                    master[c0 - n0: c1 - n0] += wet
                    if stems:
                        buses["reverb"][c0 - n0: c1 - n0] += wet
        for i, v in enumerate(voices):
            infos[i] = [r.info for r in v]
    else:
        sample_len = {src.id: signals.sample_stats(src.params["sample"])[2] * rate / src.params["pitch"]
                      for src in active}
        far_ids = [i for i, src in enumerate(active) if src.spatial and not near[i].all()]
        far = farfield.FarField(scene, ctx, active, far_ids)
        gate = None  # per far source and decision block: False where culling skips it
        if cull_db is not None:
            spatial = np.array([src.spatial for src in active])
            gate = ~skip_mask(levels[1], [src.group for src in active], cull_db, cullable=spatial)
        t_loaded = time.perf_counter()
        n_chunks = len(chunks)
        tier_fade = int(round(farfield.TIER_FADE_S * rate))
        # near runs: (source, first chunk, last chunk); a renderer per run lives from its first chunk
        # (warm-up before it) to the crossfade at the start of the chunk after its last
        runs: dict[int, list[tuple[int, int]]] = {}
        for i in range(len(active)):
            row = near[i]
            ci = 0
            while ci < n_chunks:
                if row[ci]:
                    cj = ci
                    while cj + 1 < n_chunks and row[cj + 1]:
                        cj += 1
                    runs.setdefault(ci, []).append((i, ci, cj))
                    ci = cj + 1
                else:
                    ci += 1
        alive: dict[int, tuple[list, int]] = {}  # source -> (renderers, last chunk of its run)
        run_stats = {"runs": sum(len(v) for v in runs.values()), "max_alive": 0}

        def start_runs(ci: int, pool) -> None:
            todo = runs.get(ci, [])
            if not todo:
                return
            c_start = r0 if ci == 0 else chunks[ci][0]
            c_end = []
            for _, _, cj in todo:
                c_end.append(chunks[cj][1] + (tier_fade if cj + 1 < n_chunks else 0))

            def make(k: int):
                i, _, cj = todo[k]
                src = active[i]
                if not src.spatial:
                    return build(src)[0]
                a = c_start - int(math.ceil(WARMUP_S * rate)) - 4 * step
                j0 = max(grid.index_of(a) - 3, 0)
                j1 = min(grid.index_of(min(c_end[k], n1)) + 4, grid.count - 1)
                sub = ctx.geometry.sub(j0, j1 - j0 + 1)
                c = RenderContext(scene=scene, grid=sub.grid, geometry=sub, interp=interp, panner=ctx.panner,
                                  rate=rate, send=send_law, output_start=max(n0, c_start))
                return build(src, c)[0]

            made = list(pool.map(make, range(len(todo))))
            for (i, _, cj), rs in zip(todo, made):
                alive[i] = (rs, cj)
            run_stats["max_alive"] = max(run_stats["max_alive"], sum(len(rs) for rs, _ in alive.values()))

        def near_chunk(i: int, ci: int | None, c0: int, c1: int):
            """Source i's near renderers over [c0, c1): the whole chunk while near (crossfading in at
            the start of a run), only the crossfade out in the chunk after a run; and its send."""
            rs, last = alive[i]
            ending = ci is not None and ci > last
            first = ci is not None and ci > 0 and not near[i, ci - 1] and not ending
            b = min(c1, c0 + tier_fade) if ending else c1
            contrib, send = None, None
            for r in rs:
                y, sd = r.render(c0, b)
                if ending or first:
                    fin, fout = farfield.crossfade((np.arange(c0, b) - c0) / tier_fade,
                                                   farfield.coherence(active[i].params, s["panner"]))
                    w = fout if ending else fin
                    y = y * w[:, None]
                    sd = sd * w if sd is not None else None
                contrib = y if contrib is None else contrib + y
                if sd is not None:
                    send = sd if send is None else send + sd
            if contrib is not None and b < c1:
                contrib = np.concatenate([contrib, np.zeros((c1 - b, 2))])
                send = np.concatenate([send, np.zeros(c1 - b)]) if send is not None else None
            if contrib is not None and ci is not None:
                note_peaks(i, contrib, c0, c1)
            return contrib, send

        def far_parts(ci: int) -> list:
            parts = []
            for i in far_ids:
                now, prev = near[i, ci], ci > 0 and near[i, ci - 1]
                if now and (ci == 0 or prev):
                    continue
                g = None
                if gate is not None and not now:
                    g = gate[i, [k for k, (_, _, cc) in enumerate(spans) if cc == ci]]
                for vi in far.by_source[i]:
                    parts.append(farfield.Part(vi, fade_in=bool(prev and not now), fade_out=bool(now), gate=g))
            return parts

        def far_chunk(ci: int | None, c0: int, c1: int, pool):
            parts = far_parts(0 if ci is None else ci)
            chunk_spans = [sp for sp in spans if sp[2] == ci] if ci is not None else None
            if ci is None:
                parts = [farfield.Part(pt.voice, fade_in=False, fade_out=pt.fade_out) for pt in parts
                         if not pt.fade_in]
            mixed, sends, peaks = far.render(parts, c0, c1, chunk_spans, pool)
            if ci is not None:
                j0 = grid.index_of(c0)
                ctl_blocks = (grid.samples[j0: j0 + 1] - n0) // step
                for vi, pk in peaks.items():
                    blocks = np.clip(ctl_blocks[0] + np.arange(len(pk)), 0, max(n_blocks - 1, 0))
                    i = far.voices[vi].source
                    np.maximum.at(frame_peak[i], block_frame[blocks], pk)
            return mixed, sends

        with ThreadPoolExecutor(max_workers=max(1, min(workers or os.cpu_count() or 1, 64))) as pool:
            start_runs(0, pool)
            for c0 in range(r0, n0, chunk):  # pre-roll: only the reverb bus keeps what it gets
                c1 = min(c0 + chunk, n0)
                ids = sorted(alive)
                sends = [sd for _, sd in pool.map(lambda i: near_chunk(i, None, c0, c1), ids)]
                _, far_sends = far_chunk(None, c0, c1, pool)
                total = sum((sd for sd in sends if sd is not None), np.zeros(c1 - c0))
                for g in groups:
                    if g in far_sends:
                        total = total + far_sends[g]
                bus.process(total)
            for ci, (c0, c1) in enumerate(chunks):
                if ci > 0:
                    start_runs(ci, pool)
                ids = sorted(alive)
                send_sum = np.zeros(c1 - c0)
                for i, (contrib, send) in zip(ids, pool.map(lambda i: near_chunk(i, ci, c0, c1), ids)):
                    if contrib is not None:
                        mix_chunk(i, contrib, c0, c1)
                    if send is not None:
                        send_sum += send
                mixed, far_sends = far_chunk(ci, c0, c1, pool)
                for g in groups:  # in group order: deterministic
                    if g in mixed:
                        master[c0 - n0: c1 - n0] += mixed[g]
                        if stems:
                            buses[g][c0 - n0: c1 - n0] += mixed[g]
                    if g in far_sends:
                        send_sum += far_sends[g]
                if bus is not None:
                    wet = bus.process(send_sum)
                    master[c0 - n0: c1 - n0] += wet
                    if stems:
                        buses["reverb"][c0 - n0: c1 - n0] += wet
                for i in [i for i, (_, last) in alive.items() if ci > last]:  # their crossfade out is done
                    infos[i] += [_summary(r.info) for r in alive.pop(i)[0]]
        for i, (rs, _) in alive.items():
            infos[i] += [_summary(r.info) for r in rs]
        for v in far.voices:
            if v.stats:
                infos[v.source].append({"distance": np.array(v.stats["distance"]), "rate": np.array(v.stats["rate"]),
                                        "delay": np.array(v.stats["delay"]), "clamped": 0, "before_bake": 0})
        far_chunks = int(np.sum(~near[far_ids])) if far_ids else 0
        lod = {"detail_voices": detail, "far_sources": len(far_ids), "far_voices": len(far.voices),
               "far_share": round(far_chunks / max(len(active) * n_chunks, 1), 4), "near_runs": run_stats["runs"],
               "near_voices_max": run_stats["max_alive"]}
    master_gain = float(filters.db_to_gain(s["master_gain_db"]))
    master *= master_gain
    for b in buses.values():
        b *= master_gain
    bad = ~np.isfinite(master).all(axis=1)
    if bad.any():  # a sample with non-finite values, or a diverging filter: keep the file usable
        where = np.nonzero(bad)[0]
        warnings.append(f"{len(where)} non-finite output samples ({(where[0] + n0) / rate:.2f}-"
                        f"{(where[-1] + n0) / rate:.2f} s after the first frame) replaced by silence: a sample "
                        "file with non-finite values, or a render that diverged (please report it with the scene)")
        master[bad] = 0.0
        for b in buses.values():
            b[~np.isfinite(b).all(axis=1)] = 0.0
    peak = float(np.abs(master).max()) if master.size else 0.0
    if peak > OVERLOAD_GAIN:
        warnings.append(f"master peak {filters.gain_to_db(peak):+.1f} dBFS, far above full scale: check the gains, "
                        "or a render that diverged (please report it with the scene)")
    t_dsp = time.perf_counter()

    before_bake: list[tuple[float, str]] = []
    stats: dict[str, dict] = {}
    fb_ok = np.array(frame_blocks[1:]) > np.array(frame_blocks[:-1])
    threshold = float(filters.db_to_gain(AUDIBLE_DBFS))
    chunk_s = np.array([(c1 - c0) / rate for c0, c1 in chunks])
    total_s = (n1 - n0) / rate
    culled_whole = 0
    non_finite: list[str] = []
    for i, src in enumerate(active):
        fp = frame_peak[i] * master_gain  # the source's peaks as they are in the output
        if not np.isfinite(fp).all():
            non_finite.append(src.id)
            fp = np.where(np.isfinite(fp), fp, 0.0)
        audible = int(np.sum((fp > threshold) & fb_ok)) if n_blocks else 0
        st = {
            "id": src.id,
            "group": src.group,
            "sample": os.path.basename(src.params["sample"]),
            "mode": src.params["mode"],
            "spatial": src.spatial,
            "active_frames": _active_frames(src, sample_len[src.id], scene, fa, fb),
            "peak_dbfs": round(float(filters.gain_to_db(fp.max() if n_blocks else 0.0)), 2),
            "audible_frames": audible,
        }
        whole = False
        if keep is not None:
            culled = float(np.sum(chunk_s[~keep[i].any(axis=0)]))
            st["culled_s"] = round(culled, 2)
            whole = culled >= total_s - 1e-9
            culled_whole += whole
        if src.spatial and infos[i]:
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
            # for the debug plot (dropped from the report); far-field-only sources have none
            st["_track"] = next((x["track"] for x in infos[i] if x.get("track") is not None), None)
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
    if non_finite:
        warnings.append(f"non-finite samples came from {', '.join(non_finite)}")
    if before_bake:
        worst, worst_id = max(before_bake)
        warnings.append(f"{len(before_bake)} source(s) need positions from before the baked range (up to "
                        f"{worst:.2f} s, {worst_id}); positions are held there. Re-bake with --pad "
                        f"{math.ceil(worst * 10) / 10:g} for exact delays and Doppler at the start")
    culling = None
    if cull_db is not None:
        n_voices = sum(len(k) for k in keep) + len(skipped) if keep is not None else 0
        rendered = sum(int(k.sum()) for k in keep) if keep is not None else 0
        culling = {"cull_db": cull_db, "sources": len(selected), "skipped_before_setup": len(skipped),
                   "skipped_entirely": len(skipped) + culled_whole,
                   "rendered_share": round(rendered / max(n_voices * len(chunks), 1), 4) if lod is None else None}
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
        lod=lod,
    )


def _summary(info: dict) -> dict:
    """A near renderer's statistics with its per-control-point arrays reduced to their range (a bed's
    renderer has none)."""
    out = dict(info)
    for key in ("distance", "rate", "delay"):
        x = info.get(key)
        if x is not None:
            out[key] = np.array([x.min(), x.max()]) if len(x) else x
    return out
