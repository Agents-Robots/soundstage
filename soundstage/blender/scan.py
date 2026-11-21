"""Scan a Blender shot for sound-source candidates: cameras, moving objects, static objects near the camera.

Run headless (or through ``soundstage scan``)::

    blender -b shot.blend --factory-startup -y --python-exit-code 1 \
        --python soundstage/blender/scan.py -- --out scan.json [--frames A-B] [--samples N] \
        [--max-static N] [--run script.py ...] [--scene NAME]

Samples the shot at evenly spaced frames and writes a JSON summary: frame range and fps, cameras
and when they are active, objects that move (path length, speed, distance range to the camera,
closest frame, side at the closest frame, keyframes; those attached to the camera last), the static
objects closest to the camera path, existing sound tags, Speaker objects, and tags that come in
through instances. An agent reads it to decide which objects get which sounds
(docs/agent-guide.md). Distances are in metres.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def _import_package() -> None:
    """Import ``soundstage`` from its own folder. Putting the folder above it on ``sys.path`` would
    expose the venv's site-packages after ``pip install``, whose numpy (built for the venv's Python)
    then shadows Blender's own (#49)."""
    if "soundstage" in sys.modules:
        return
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("soundstage", root / "__init__.py",
                                                  submodule_search_locations=[str(root)])
    module = importlib.util.module_from_spec(spec)
    sys.modules["soundstage"] = module
    spec.loader.exec_module(module)


_import_package()

import bpy  # noqa: E402
import numpy as np  # noqa: E402

from soundstage.blender import emitters, tag, util  # noqa: E402
from soundstage.blender.util import log  # noqa: E402

MOVING_THRESHOLD_M = 0.01


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="scan.py")
    p.add_argument("--out", required=True)
    p.add_argument("--frames")
    p.add_argument("--samples", type=int, default=60, help="number of sampled frames")
    p.add_argument("--max-static", type=int, default=30, help="static objects to list")
    p.add_argument("--run", action="append", default=[])
    p.add_argument("--scene", help="scene name (default: the active scene)")
    return p.parse_args(argv)


def keyframes(obj, limit: int = 30) -> list[float]:
    """Frames of the object's own keyframes (location, rotation, scale and others), if any."""
    ad = obj.animation_data
    if not ad or not ad.action:
        return []
    fcurves = []
    try:
        from bpy_extras import anim_utils

        bag = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
        fcurves = list(bag.fcurves) if bag else []
    except Exception:
        fcurves = list(getattr(ad.action, "fcurves", []))
    frames = sorted({round(k.co[0], 3) for fc in fcurves for k in fc.keyframe_points})
    return frames[:limit]


def side(q: np.ndarray) -> str:
    """Rough direction of a camera-space vector (+X right, +Y up, -Z forward)."""
    x, _, z = q
    lr = "right" if x > 0 else "left"
    fb = "front" if z < 0 else "behind"
    return f"{fb}-{lr}" if abs(x) > 0.25 * abs(z) else fb


def speaker_info(obj) -> dict:
    """What a Speaker object will play (read as a source by the bake unless muted)."""
    spk = obj.data
    frames = []
    if obj.animation_data:
        for track in obj.animation_data.nla_tracks:
            if not track.mute:
                frames += [s.frame_start for s in track.strips if s.type == "SOUND" and not s.mute]
    sound = spk.sound
    return {
        "name": obj.name,
        "sound": None if sound is None else (sound.name if sound.packed_file else bpy.path.abspath(sound.filepath)),
        "packed": bool(sound and sound.packed_file),
        "strip_frames": sorted(float(f) for f in frames),
        "muted": spk.muted,
        "volume": spk.volume,
        "overrides": tag._plain(obj.get("sfx_speaker")),
    }


def scan(args: argparse.Namespace) -> None:
    util.activate_scene(args.scene)
    util.run_scripts(args.run)
    scene = bpy.context.scene
    frame_start, frame_end = util.parse_frames(args.frames, scene)
    scale = scene.unit_settings.scale_length or 1.0
    count = max(2, min(args.samples, frame_end - frame_start + 1))
    sample_frames = np.unique(np.round(np.linspace(frame_start, frame_end, count)).astype(int))

    objs = [o for o in scene.objects if o.type != "CAMERA"]
    pos = np.zeros((len(sample_frames), len(objs), 3))
    cam_pos = np.zeros((len(sample_frames), 3))
    cam_rot = np.zeros((len(sample_frames), 3, 3))
    cam_names: list[str | None] = []
    original_frame = scene.frame_current
    log(f"scanning {len(objs)} objects at {len(sample_frames)} frames")
    for k, f in enumerate(sample_frames):
        scene.frame_set(int(f))
        dg = bpy.context.evaluated_depsgraph_get()
        cam = scene.camera
        cam_names.append(cam.name if cam else None)
        if cam:
            loc, rot, _ = cam.evaluated_get(dg).matrix_world.decompose()
            cam_pos[k] = np.array(loc) * scale
            cam_rot[k] = np.array(rot.to_matrix())
        for j, o in enumerate(objs):
            pos[k, j] = np.array(o.evaluated_get(dg).matrix_world.translation) * scale
    scene.frame_set(original_frame)

    cameras = []
    for name in dict.fromkeys(n for n in cam_names if n):
        active = [int(f) for f, n in zip(sample_frames, cam_names) if n == name]
        cameras.append({"name": name, "first_sampled_frame": active[0], "last_sampled_frame": active[-1]})

    rel = pos - cam_pos[:, None, :]
    dist = np.linalg.norm(rel, axis=2)
    q = np.einsum("kji,koj->koi", cam_rot, rel)  # camera space: R^T (s - p)
    steps = np.linalg.norm(np.diff(pos, axis=0), axis=2)
    path = steps.sum(axis=0)
    dt = np.diff(sample_frames) / util.fps(scene)
    speed = (steps / dt[:, None]).max(axis=0) if len(dt) else np.zeros(len(objs))

    def describe(j: int) -> dict:
        o = objs[j]
        kmin = int(dist[:, j].argmin())
        return {
            "name": o.name,
            "type": o.type,
            "parent": o.parent.name if o.parent else None,
            "collections": util.collections_of(o),
            "dimensions_m": [round(float(d) * scale, 3) for d in o.dimensions],
            "hide_render": o.hide_render,
            "distance_m": [round(float(dist[:, j].min()), 2), round(float(dist[:, j].max()), 2)],
            "closest_frame": int(sample_frames[kmin]),
            "side_at_closest": side(q[kmin, j]),
        }

    moving, static = [], []
    for j, o in enumerate(objs):
        if path[j] > MOVING_THRESHOLD_M:
            moved = np.nonzero(steps[:, j] > MOVING_THRESHOLD_M / len(steps))[0]
            d = describe(j)
            d.update({
                "path_length_m": round(float(path[j]), 2),
                "max_speed_m_s": round(float(speed[j]), 2),
                "moving_frames": [int(sample_frames[moved[0]]), int(sample_frames[moved[-1] + 1])],
                "moves_with_camera": bool(np.ptp(dist[:, j]) < 0.01 and np.linalg.norm(np.ptp(q[:, j], axis=0)) < 0.01),
                "keyframes": keyframes(o),
            })
            moving.append(d)
        else:
            static.append(j)
    moving.sort(key=lambda d: (d["moves_with_camera"], d["distance_m"][0]))  # camera rig last
    static.sort(key=lambda j: dist[:, j].min())

    tagged = [{"object": o.name, "index": i, "entry": e} for o, i, e in tag.iter_tagged(scene)]
    speakers = [speaker_info(o) for o in emitters.view_layer_objects(scene) if o.type == "SPEAKER"]
    instanced: dict[str, int] = {}
    for em in emitters.instances(scene, 0, [], scale)[0]:
        instanced[em.obj.name] = instanced.get(em.obj.name, 0) + 1
    cam_steps = np.linalg.norm(np.diff(cam_pos, axis=0), axis=1)
    result = {
        "blend_file": bpy.data.filepath,
        "scene": scene.name,
        "fps": util.fps(scene),
        "frame_start": frame_start,
        "frame_end": frame_end,
        "duration_s": round((frame_end - frame_start + 1) / util.fps(scene), 3),
        "scale_length": scale,
        "sampled_frames": len(sample_frames),
        "cameras": cameras,
        "camera_path": {
            "start_m": [round(float(c), 2) for c in cam_pos[0]],
            "end_m": [round(float(c), 2) for c in cam_pos[-1]],
            "length_m": round(float(cam_steps.sum()), 2),
            "max_speed_m_s": round(float((cam_steps / dt).max()), 2) if len(dt) else 0.0,
        },
        "counts": {"objects": len(objs), "moving": len(moving), "static": len(static)},
        "moving": moving,
        "static_near": [describe(j) for j in static[: args.max_static]],
        "scene_settings": tag.get_scene_settings(scene),
        "tagged": tagged,
        "speakers": speakers,
        "instanced_tags": [{"object": k, "instances": v} for k, v in sorted(instanced.items())],
    }
    util.write_json(Path(args.out).resolve(), result)
    log(f"wrote {Path(args.out).resolve()}")


if __name__ == "__main__":
    scan(parse_args(util.script_args()))
