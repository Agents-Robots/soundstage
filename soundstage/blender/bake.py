"""Bake a Blender shot into a scene file (scene.json + scene.npz) for the engine.

Run headless (or through ``soundstage bake``)::

    blender -b shot.blend --factory-startup -y --python-exit-code 1 \
        --python soundstage/blender/bake.py -- --out audio/bake/shot1 \
        [--frames A-B] [--substeps N] [--pad SECONDS] [--run tag_script.py ...] [--skip-invalid]

Steps: run tagging scripts (``--run``, not saved to the .blend), validate tags and resolve their
defaults and sample paths, step through frames and sub-frames over the shot plus padding, record
the listener (active camera per frame) and every emitter's world position in metres, record camera
switches as cuts, write the scene file (docs/spec/scene-format.md).

Uses bpy, stdlib and Blender's bundled numpy only.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from soundstage.blender import schema, tag, util  # noqa: E402
from soundstage.blender.util import log  # noqa: E402

FORMAT = "soundstage.scene"
VERSION = 1


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


def padding_warnings(spatial: list[dict], listener_matrix, src_pos, speed_of_sound: float,
                     pad_seconds: float) -> list[str]:
    """One warning if sources are farther away (in travel time) than the padding covers."""
    if not spatial:
        return []
    delay = np.linalg.norm(src_pos - listener_matrix[:, None, :3, 3], axis=2).max(axis=0) / speed_of_sound
    over = np.nonzero(delay > pad_seconds)[0]
    if not len(over):
        return []
    worst = int(over[np.argmax(delay[over])])
    return [f"padding {pad_seconds:.2f} s is shorter than the travel time of {len(over)} source(s) (up to "
            f"{delay[worst]:.2f} s, {spatial[worst]['id']}); bake with --pad {math.ceil(delay[worst] * 10) / 10:g} "
            "for exact delays and Doppler at the start of the shot"]


def resolve_sample_path(sample: str, samples_root: str) -> str:
    if sample.startswith("//"):
        return os.path.normpath(bpy.path.abspath(sample))
    if os.path.isabs(sample):
        return os.path.normpath(sample)
    return os.path.normpath(os.path.join(bpy.path.abspath(samples_root), sample))


def collect_sources(scene, settings: dict, skip_invalid: bool) -> tuple[list[dict], list[str]]:
    """Validated, resolved sources and warnings. Exits with all errors listed if any are fatal."""
    sources, errors, warnings, seen = [], [], [], set()
    for obj, index, entry in tag.iter_tagged(scene):
        where = f"{obj.name}[{index}]"
        problems = schema.validate_source(entry)
        resolved = None
        if not problems:
            resolved = schema.resolve_source(entry, default_id=f"{obj.name}:{index}")
            resolved["sample"] = resolve_sample_path(resolved["sample"], settings["samples_root"])
            if not os.path.isfile(resolved["sample"]):
                problems.append(f"sample not found: {resolved['sample']}")
            if resolved["id"] in seen:
                problems.append(f"duplicate id {resolved['id']!r}")
        if problems:
            (warnings if skip_invalid else errors).extend(f"{where}: {m}" for m in problems)
            continue
        seen.add(resolved["id"])
        sources.append({"object": obj.name, "index": index, **resolved})
    if errors:
        for e in errors:
            log(f"ERROR {e}")
        raise SystemExit(1)
    return sources, warnings


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

    sources, warnings = collect_sources(scene, settings, args.skip_invalid)
    for w in warnings:
        log(f"WARNING {w}")
    if not sources:
        log("WARNING no sound tags found")

    frame_start, frame_end = util.parse_frames(args.frames, scene)
    fps = util.fps(scene)
    substeps = int(settings["substeps"])
    pad = math.ceil(settings["pad_seconds"] * fps)
    scale = scene.unit_settings.scale_length or 1.0

    spatial = [s for s in sources if s["spatial"]]
    for track, s in enumerate(spatial):
        s["track"] = track
    for s in sources:
        s.setdefault("track", None)
    objects = [scene.objects[s["object"]] for s in spatial]
    offsets = [Vector(s["offset"]) for s in spatial]
    axes = [AXIS_VECTORS[s["forward_axis"]] for s in spatial]

    first, last = frame_start - pad, frame_end + pad
    n = (last - first) * substeps + 1
    frames = first + np.arange(n) / substeps
    listener_matrix = np.zeros((n, 4, 4))
    listener_index = np.zeros(n, dtype=np.int16)
    src_pos = np.zeros((n, len(spatial), 3))
    src_fwd = np.zeros((n, len(spatial), 3), dtype=np.float32)
    listener_names: list[str] = []
    cuts: list[float] = []

    original_frame = scene.frame_current
    log(f"baking frames {first}..{last} x{substeps} ({n} samples), {len(spatial)} spatial sources")
    for k, f in enumerate(frames):
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
        for j, (obj, off, axis) in enumerate(zip(objects, offsets, axes)):
            mw = obj.evaluated_get(depsgraph).matrix_world
            src_pos[k, j] = np.array(mw @ off) * scale
            fwd = mw.to_3x3() @ axis
            src_fwd[k, j] = np.array(fwd.normalized() if fwd.length > 1e-12 else axis)
    scene.frame_set(original_frame)

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out / "scene.npz",
        frames=frames,
        listener_matrix=listener_matrix,
        listener_index=listener_index,
        cuts=np.array(cuts, dtype=np.float64),
        src_pos=src_pos,
        src_fwd=src_fwd,
        src_cuts=np.zeros((0, 2)),
    )
    for w in padding_warnings(spatial, listener_matrix, src_pos, settings["speed_of_sound"], pad / fps):
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
