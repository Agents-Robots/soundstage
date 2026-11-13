"""Bake a Blender shot into a scene file (scene.json + scene.npz) for the engine.

Run headless (or through ``soundstage bake``)::

    blender -b shot.blend --factory-startup -y --python-exit-code 1 \
        --python soundstage/blender/bake.py -- --out audio/bake/shot1 \
        [--frames A-B] [--substeps N] [--pad SECONDS] [--run tag_script.py ...] [--skip-invalid]

Steps: run tagging scripts (``--run``, not saved to the .blend), validate tags and resolve their
defaults and sample paths, step through frames and sub-frames over the shot plus padding, record
the listener (active camera per frame) with its frame edges and every emitter's world position in
metres, record camera switches as cuts, sample each source's visibility (occlusion.py) at ``occlusion_rate`` (only for
sources that may be heard, cull.py), write the scene file (docs/spec/scene-format.md).

Uses bpy, stdlib and Blender's bundled numpy only.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from soundstage.blender import cull, emitters, occlusion, schema, tag, util  # noqa: E402
from soundstage.blender.util import log  # noqa: E402

FORMAT = "soundstage.scene"
VERSION = 2


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="bake.py")
    p.add_argument("--out", required=True, help="output directory for scene.json and scene.npz")
    p.add_argument("--frames", help="frame range A-B (default: scene range)")
    p.add_argument("--substeps", type=int, help="sub-frames per frame (default: scene setting)")
    p.add_argument("--pad", type=float, help="padding in seconds before and after (default: scene setting)")
    p.add_argument("--run", action="append", default=[], help="script to run before baking")
    p.add_argument("--scene", help="scene name (default: the active scene)")
    p.add_argument("--skip-invalid", action="store_true", help="drop invalid tags instead of failing")
    return p.parse_args(argv)


AXIS_VECTORS = {
    "X": Vector((1, 0, 0)), "-X": Vector((-1, 0, 0)),
    "Y": Vector((0, 1, 0)), "-Y": Vector((0, -1, 0)),
    "Z": Vector((0, 0, 1)), "-Z": Vector((0, 0, -1)),
}


def frame_edges(listener, scene) -> tuple[float, float]:
    """x / -z of the left and right frame edges of an evaluated perspective camera (lens, sensor fit,
    render aspect and shift included); NaN for other listeners."""
    data = getattr(listener, "data", None)
    if listener.type != "CAMERA" or data.type != "PERSP":
        return math.nan, math.nan
    corners = data.view_frame(scene=scene)
    xs, z = [c.x for c in corners], corners[0].z
    return min(xs) / -z, max(xs) / -z


def padding_warnings(spatial: list[dict], frames, listener_matrix, src_pos, speed_of_sound: float, frame_start: float,
                     fps: float, pad_seconds: float) -> list[str]:
    """One warning if sound heard from ``frame_start`` on was emitted earlier than the padding covers.

    Per source, the sound heard at each baked sample was emitted its travel time earlier (from the
    position at the sample: close enough for a warning). The padding has to reach back to the
    earliest such emission before ``frame_start`` that falls while the source is active (from its
    ``frame``, the first trigger of a one-shot, to its ``end_frame``); a source that starts at or
    after ``frame_start`` needs none. Distances to the cameras of other shots do not count.
    """
    if not spatial:
        return []
    heard = frames >= frame_start
    tau = np.linalg.norm(src_pos[heard] - listener_matrix[heard][:, None, :3, 3], axis=2) / speed_of_sound
    emitted = frames[heard][:, None] - tau * fps
    starts, ends = [], []
    for s in spatial:
        f = s.get("frame")
        starts.append(-np.inf if f is None else min(f) if isinstance(f, list) else float(f))
        ends.append(np.inf if s.get("end_frame") is None or s["mode"] != "loop" else float(s["end_frame"]))
    early = (emitted < frame_start) & (emitted >= np.array(starts)) & (emitted <= np.array(ends))
    need = np.where(early, (frame_start - emitted) / fps, 0.0).max(axis=0)
    over = np.nonzero(need > pad_seconds)[0]
    if not len(over):
        return []
    worst = int(over[np.argmax(need[over])])
    return [f"padding {pad_seconds:.2f} s is shorter than the travel time of {len(over)} source(s) heard from before "
            f"the first frame (up to {need[worst]:.2f} s, {spatial[worst]['id']}); bake with --pad "
            f"{math.ceil(need[worst] * 10) / 10:g} for exact delays and Doppler at the start of the shot"]


def resolve_sample_path(sample: str, samples_root: str) -> str:
    if sample.startswith("//"):
        return os.path.normpath(bpy.path.abspath(sample))
    if os.path.isabs(sample):
        return os.path.normpath(sample)
    return os.path.normpath(os.path.join(bpy.path.abspath(samples_root), sample))


def collect_sources(scene, settings: dict, skip_invalid: bool, out: Path, frame_range: tuple[int, int],
                    scale: float) -> tuple[list[dict], list[emitters.Emitter], list[str]]:
    """Validated, resolved sources with their emitters, and warnings. Exits listing all fatal errors."""
    found = emitters.tagged_objects(scene)
    warnings = []
    if settings["read_speakers"]:
        spk, w = emitters.speakers(scene, out / "sounds")
        found += spk
        warnings += w
    inst, w = emitters.instances(scene, int(settings["instance_limit"]),
                                 emitters.sample_frames(*frame_range), scale)
    found += inst
    warnings += w
    sources, owners, errors, seen = [], [], [], set()
    for em in found:
        for index, entry in em.entries:
            where = f"{em.label}[{index}]"
            problems = schema.validate_source(entry)
            resolved = None
            if not problems:
                resolved = schema.resolve_source(entry, default_id=f"{em.label}:{index}")
                resolved["sample"] = resolve_sample_path(resolved["sample"], settings["samples_root"])
                if not os.path.isfile(resolved["sample"]):
                    problems.append(f"sample not found: {resolved['sample']}")
                if resolved["id"] in seen:
                    problems.append(f"duplicate id {resolved['id']!r}")
            if problems:
                (warnings if skip_invalid else errors).extend(f"{where}: {m}" for m in problems)
                continue
            seen.add(resolved["id"])
            sources.append({"object": em.label, "index": index, **resolved})
            owners.append(em)
    if errors:
        for e in errors:
            log(f"ERROR {e}")
        raise SystemExit(1)
    return sources, owners, warnings


def bake(args: argparse.Namespace) -> None:
    util.activate_scene(args.scene)
    util.run_scripts(args.run)
    scene = bpy.context.scene

    raw_settings = tag.get_scene_settings(scene)
    errors = schema.validate_settings(raw_settings)
    if errors:
        for e in errors:
            log(f"ERROR scene settings: {e}")
        raise SystemExit(1)
    settings = schema.resolve_settings(raw_settings)
    if args.substeps is not None:
        settings["substeps"] = args.substeps
    if args.pad is not None:
        settings["pad_seconds"] = args.pad

    frame_start, frame_end = util.parse_frames(args.frames, scene)
    fps = util.fps(scene)
    substeps = int(settings["substeps"])
    pad = math.ceil(settings["pad_seconds"] * fps)
    scale = scene.unit_settings.scale_length or 1.0
    out = Path(args.out).resolve()

    sources, owners, warnings = collect_sources(scene, settings, args.skip_invalid, out, (frame_start, frame_end), scale)
    for w in warnings:
        log(f"WARNING {w}")
    if not sources:
        log("WARNING no sound tags or speakers found")

    spatial = [s for s in sources if s["spatial"]]
    for track, s in enumerate(spatial):
        s["track"] = track
    for s in sources:
        s.setdefault("track", None)
    objects = [em for em, s in zip(owners, sources) if s["spatial"]]
    slow_keys = {(e.instancer.name, e.pid) for e in objects if e.instancer is not None and not e.fast}
    offsets = [Vector(s["offset"]) for s in spatial]
    axes = [AXIS_VECTORS[s["forward_axis"]] for s in spatial]

    first, last = frame_start - pad, frame_end + pad
    n = (last - first) * substeps + 1
    frames = first + np.arange(n) / substeps
    listener_matrix = np.zeros((n, 4, 4))
    listener_index = np.zeros(n, dtype=np.int16)
    listener_frame = np.full((n, 2), np.nan)  # x / -z of the frame's left and right edges
    src_pos = np.zeros((n, len(spatial), 3))
    src_fwd = np.zeros((n, len(spatial), 3), dtype=np.float32)
    listener_names: list[str] = []
    cuts: list[float] = []

    occluding = [j for j, s in enumerate(spatial) if s["occlusion"]]
    occluders, vis_frames, vis, vis_seconds, update_seconds = None, [], [], 0.0, 0.0
    blockers = [Counter() for _ in spatial]  # per source: blocked paths by object, over the shot
    vis_step = max(1, round(fps * substeps / settings["occlusion_rate"])) if settings["occlusion_rate"] > 0 else 0
    if occluding and vis_step:
        t0 = time.perf_counter()
        occluders = occlusion.Occluders(scene, [float(first), (first + last) / 2, float(last)],
                                        settings["occluder_min_size"], scale, settings["listener"])
        log(f"occluders: {occluders.counts['static']} static, {occluders.counts['moving']} moving boxes, "
            f"{occluders.counts['carried']} travelling with the listener ({time.perf_counter() - t0:.1f} s; "
            f"{occluders.walked} moving boxes looked up per sample in the instances); "
            f"visibility every {vis_step} samples")
    radii = [spatial[j]["occlusion_radius"] for j in occluding]
    culler = None
    if occluders is not None and (settings["cull_db"] is not None or settings["detail_voices"] is not None):
        try:
            culler = cull.Culler(spatial, occluding, settings, fps)
        except Exception as e:  # a sample aud cannot decode: compute every source's visibility
            w = f"culling off in the bake: sample levels not readable ({e})"
            log(f"WARNING {w}")
            warnings.append(w)

    original_frame = scene.frame_current
    log(f"baking frames {first}..{last} x{substeps} ({n} samples), {len(spatial)} spatial sources")
    t_start, report_every = time.perf_counter(), max(1, n // 10)
    for k, f in enumerate(frames):
        if k and k % report_every == 0:
            spent = time.perf_counter() - t_start
            log(f"  {k}/{n} samples, {spent:.0f} s, about {spent * (n - k) / k:.0f} s to go")
        util.set_frame(scene, float(f))
        depsgraph = bpy.context.evaluated_depsgraph_get()
        listener = util.listener_object(scene, settings["listener"])
        if listener is None:
            log(f"ERROR no active camera at frame {f}")
            raise SystemExit(1)
        if listener.name not in listener_names:
            listener_names.append(listener.name)
        li = listener_names.index(listener.name)
        if k > 0 and li != listener_index[k - 1]:
            cuts.append(float(f))
        listener_index[k] = li
        loc, rot, _ = listener.evaluated_get(depsgraph).matrix_world.decompose()
        m = Matrix.LocRotScale(loc * scale, rot, None)
        listener_matrix[k] = np.array(m)
        listener_frame[k] = frame_edges(listener.evaluated_get(depsgraph), scene)
        lookup = emitters.instance_lookup(depsgraph, slow_keys) if slow_keys else None
        matrices: dict[int, Matrix] = {}  # per emitter: several sources on one object share it
        for j, (em, off, axis) in enumerate(zip(objects, offsets, axes)):
            mw = matrices.get(id(em))
            if mw is None:
                mw = matrices[id(em)] = em.matrix(depsgraph, lookup)
            src_pos[k, j] = np.array(mw @ off) * scale
            fwd = mw.to_3x3() @ axis
            src_fwd[k, j] = np.array(fwd.normalized() if fwd.length > 1e-12 else axis)
        if occluders is not None and k % vis_step == 0:
            # the path of the sound heard now: from where the source emitted it to the listener and occluders now
            t_vis = time.perf_counter()
            occluders.update(depsgraph, frames[k] / fps, np.array(loc), settings["speed_of_sound"] / scale)
            update_seconds += time.perf_counter() - t_vis
            emitted = occlusion.retarded_positions(frames[:k + 1] / fps, src_pos[:k + 1, occluding],
                                                   np.array(loc) * scale, settings["speed_of_sound"])
            v = np.ones((len(spatial), len(occlusion.BANDS_HZ)), dtype=np.float32)
            todo, direct = np.arange(len(occluding)), np.zeros(len(occluding), dtype=bool)
            if culler is not None:
                todo, direct = culler.keep(frames[k] / fps, np.array(loc) * scale, emitted, src_pos[k])
                v[np.setdiff1d(occluding, np.asarray(occluding)[todo])] = np.nan  # filled in after the loop
            for few, part in ((False, todo[~direct]), (True, todo[direct])):
                sel = [occluding[i] for i in part]
                counts = [Counter() for _ in sel]
                if not sel:
                    continue
                if few:  # far-field sources: one broadband visibility
                    v[sel] = occlusion.direct_visibility(occluders, np.array(loc), emitted[part] / scale, counts)
                else:
                    v[sel] = occlusion.visibility(occluders, np.array(loc), emitted[part] / scale,
                                                  [radii[i] for i in part], scale, settings["speed_of_sound"], counts)
                for j, c in zip(sel, counts):
                    blockers[j].update(c)
            vis_frames.append(float(f))
            vis.append(v)
            vis_seconds += time.perf_counter() - t_vis
    scene.frame_set(original_frame)
    culled_share = direct_share = None
    if vis:
        log(f"visibility: {len(vis)} samples x {len(occluding)} sources in {vis_seconds:.1f} s "
            f"({vis_seconds / len(vis) * 1000:.0f} ms per sample, {update_seconds / len(vis) * 1000:.0f} ms of it "
            f"moving the occluders)")
        if culler is not None:
            culled_share, direct_share = (None if x is None else round(x, 4) for x in culler.report())
            vis = list(cull.fill(np.array(vis, dtype=np.float32)))
    gone = [em for em in {id(em): em for em in objects}.values() if em.missing]
    if gone:
        worst = max(gone, key=lambda em: em.missing)
        w = (f"{len(gone)} instance source(s) not generated at some baked samples (up to {worst.missing} of {n}, "
             f"{worst.label}); their positions are held there")
        log(f"WARNING {w}")
        warnings.append(w)

    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out / "scene.npz",
        frames=frames,
        listener_matrix=listener_matrix,
        listener_index=listener_index,
        listener_frame=listener_frame,
        cuts=np.array(cuts, dtype=np.float64),
        src_pos=src_pos,
        src_fwd=src_fwd,
        src_cuts=np.zeros((0, 2)),
        **({"vis_frames": np.array(vis_frames), "src_visibility": np.array(vis, dtype=np.float32)} if vis else {}),
    )
    for w in padding_warnings(spatial, frames, listener_matrix, src_pos, settings["speed_of_sound"], frame_start, fps,
                              pad / fps):
        log(f"WARNING {w}")
        warnings.append(w)
    manifest = {
        "format": FORMAT,
        "version": VERSION,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": {"tool": "soundstage.blender.bake", "blender_version": util.blender_version()},
        "blend_file": bpy.data.filepath,
        "scene": scene.name,
        "time": {
            "fps": scene.render.fps,
            "fps_base": round(scene.render.fps_base, 6),  # stored as float32 in Blender
            "frame_start": frame_start,
            "frame_end": frame_end,
            "substeps": substeps,
            "pad_frames_before": pad,
            "pad_frames_after": pad,
        },
        "units": {"scale_length": scale},
        "settings": settings,
        "listener": {"objects": listener_names},
        "occlusion": ({"bands_hz": list(occlusion.BANDS_HZ), "samples": len(vis_frames),
                       "occluders": occluders.counts, "geometry": "boxes", "culled_share": culled_share,
                       "direct_share": direct_share,
                       "blockers": {s["id"]: [[name, round(n / (len(vis_frames) * occlusion.PATHS), 3)]
                                              for name, n in blockers[j].most_common(3)]
                                    for j, s in enumerate(spatial) if blockers[j]}} if vis else None),
        "sources": sources,
        "arrays": "scene.npz",
        "warnings": warnings,
    }
    util.write_json(out / "scene.json", manifest)
    for s in sources:
        where = "bed" if not s["spatial"] else f"track {s['track']}"
        f = s["frame"]
        when = "always" if f is None else f"frames {', '.join(f'{x:g}' for x in f)}" if isinstance(f, list) else f"frame {f:g}"
        log(f"source {s['id']}: {os.path.basename(s['sample'])} {s['mode']} {when} ({where})")
    log(f"wrote {out / 'scene.json'}")


if __name__ == "__main__":
    bake(parse_args(util.script_args()))
