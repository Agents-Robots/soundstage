"""Where sources come from in a Blender scene, and where they are at each baked sample.

- Tags on objects in the view layer (``obj["sfx"]``, docs/spec/tagging.md).
- Native Speaker objects (FR-8): sound file, volume, pitch, reference/maximum distance,
  attenuation, cone, mute; each unmuted NLA sound strip is a trigger frame. The scene's audio
  distance model picks the distance law. An optional ``sfx_speaker`` custom property (a dict of tag
  keys) overrides the mapping, e.g. ``{"mode": "loop", "group": "engines"}``.
- Tags inside instances (FR-9): collection instances and geometry-nodes instances found through the
  depsgraph, one source per instance; at most ``instance_limit`` per tagged object, keeping those
  that come closest to the camera.

Runs inside Blender (bpy, Blender's numpy). Model and choices: research/models/blender-integration.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix

from soundstage.blender import tag, util

NO_ID = 2 ** 31 - 1  # unused persistent-id component

DISTANCE_MODELS = {
    "INVERSE": "inverse_clamped", "INVERSE_CLAMPED": "inverse_clamped",
    "LINEAR": "linear_clamped", "LINEAR_CLAMPED": "linear_clamped",
    "EXPONENT": "exponential_clamped", "EXPONENT_CLAMPED": "exponential_clamped",
    "NONE": "none",
}


@dataclass
class Emitter:
    """One place sound comes from: an object, or an object inside an instance."""

    label: str  # object name, or "instancer/object" (and "#id" for geometry-nodes instances)
    obj: object  # original object carrying the tag or the speaker data
    instancer: object | None = None  # instancing object (collection-instance empty or geometry-nodes object)
    pid: tuple | None = None  # persistent id (geometry-nodes instances)
    fast: bool = True  # collection-instance empty: matrix by formula; otherwise from the depsgraph lookup
    entries: list = field(default_factory=list)  # (index, entry) of its tags

    def matrix(self, depsgraph, lookup: dict | None) -> Matrix:
        if self.instancer is None:
            return self.obj.evaluated_get(depsgraph).matrix_world
        if self.fast:
            coll = self.instancer.instance_collection
            inner = Matrix.Translation(-coll.instance_offset) @ self.obj.matrix_world
            return self.instancer.evaluated_get(depsgraph).matrix_world @ inner
        return lookup[(self.instancer.name, self.pid)]


def view_layer_objects(scene) -> list:
    """Objects in collections that are not excluded from the view layer. Walks the layer collections
    rather than ``view_layer.objects``, which misses objects that a ``--run`` script has just created
    until the depsgraph is evaluated."""
    layer = bpy.context.view_layer if bpy.context.view_layer and bpy.context.scene == scene else scene.view_layers[0]
    names: set[str] = set()

    def walk(lc) -> None:
        if lc.exclude:
            return
        names.update(o.name for o in lc.collection.objects)
        for child in lc.children:
            walk(child)

    walk(layer.layer_collection)
    return [o for o in sorted(scene.objects, key=lambda o: o.name) if o.name in names]


def tagged_objects(scene) -> list[Emitter]:
    out = []
    for obj in view_layer_objects(scene):
        entries = list(enumerate(tag.get_sounds(obj)))
        if entries:
            out.append(Emitter(obj.name, obj, entries=entries))
    return out


def speaker_entry(obj, scene, sound_dir: Path) -> tuple[dict | None, list[str]]:
    """Tag entry for a Speaker object (None if it plays nothing), and warnings."""
    spk, warnings = obj.data, []
    if spk.muted or spk.sound is None:
        return None, warnings
    frames = []
    if obj.animation_data:
        for track in obj.animation_data.nla_tracks:
            if track.mute:
                continue
            frames += [s.frame_start for s in track.strips if s.type == "SOUND" and not s.mute]
    if not frames:
        return None, [f"speaker {obj.name}: no unmuted NLA sound strip, skipped"]
    sound = spk.sound
    if sound.packed_file is not None:
        sound_dir.mkdir(parents=True, exist_ok=True)
        path = sound_dir / f"{bpy.path.clean_name(sound.name)}{Path(sound.filepath).suffix or '.wav'}"
        path.write_bytes(sound.packed_file.data)
    else:
        path = Path(bpy.path.abspath(sound.filepath))
    model = DISTANCE_MODELS.get(scene.audio_distance_model, "inverse_clamped")
    entry = {
        "sample": str(path),
        "mode": "once",
        "frame": sorted(float(f) for f in frames),
        "gain_db": round(20 * math.log10(max(spk.volume, 1e-6)), 3),
        "pitch": float(spk.pitch),
        "ref_distance": max(float(spk.distance_reference), 1e-3),
        "rolloff": float(spk.attenuation),
        "distance_model": model,
        "cone_inner_deg": float(spk.cone_angle_inner),
        "cone_outer_deg": float(spk.cone_angle_outer),
        "cone_outer_gain_db": round(20 * math.log10(max(spk.cone_volume_outer, 1e-6)), 3),
        "forward_axis": "-Z",
    }
    if spk.distance_max < 1e30:
        entry["max_distance"] = max(float(spk.distance_max), entry["ref_distance"])
    elif model == "linear_clamped":
        entry["distance_model"] = "inverse_clamped"
        warnings.append(f"speaker {obj.name}: linear distance model without a maximum distance; inverse used")
    if spk.volume_min > 0 or spk.volume_max < 1:
        warnings.append(f"speaker {obj.name}: volume_min/volume_max are not used")
    overrides = obj.get("sfx_speaker")
    if overrides is not None:
        entry.update(overrides.to_dict() if hasattr(overrides, "to_dict") else dict(overrides))
        if entry.get("mode") == "loop" and isinstance(entry.get("frame"), list):
            entry["frame"] = entry["frame"][0]  # a loop starts at the first strip
    return entry, warnings


def speakers(scene, sound_dir: Path) -> tuple[list[Emitter], list[str]]:
    out, warnings = [], []
    for obj in view_layer_objects(scene):
        if obj.type != "SPEAKER":
            continue
        entry, w = speaker_entry(obj, scene, sound_dir)
        warnings += w
        if entry is not None:
            entry.setdefault("id", f"{obj.name}:speaker")
            out.append(Emitter(obj.name, obj, entries=[(0, entry)]))
    return out, warnings


def instance_key(inst) -> tuple:
    """Instancer and persistent id: identifies an instance without reading ``inst.object``, which
    leaks about 125 bytes per read in Blender 5.2 (per-sample walks over large scenes add up to GB)."""
    return (inst.parent.original.name, tuple(inst.persistent_id))


def instances(scene, limit: int, sample_frames: list[float], scale: float) -> tuple[list[Emitter], list[str]]:
    """Tagged objects inside instances, at most ``limit`` per tagged object (closest to the camera)."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    found: dict[str, list[Emitter]] = {}
    for inst in depsgraph.object_instances:
        if not inst.is_instance or inst.parent is None:
            continue
        orig = inst.object.original
        parent = inst.parent.original
        if parent == orig:
            continue  # another geometry type of the object itself (e.g. mesh plus curves), not a copy
        entries = list(enumerate(tag.get_sounds(orig)))
        if not entries:
            continue
        pid = tuple(inst.persistent_id)
        top_level = len(pid) > 1 and pid[1] == NO_ID  # not nested inside another instance
        fast = top_level and parent.instance_type == "COLLECTION" and parent.instance_collection is not None and \
            orig.name in parent.instance_collection.all_objects
        label = f"{parent.name}/{orig.name}" + ("" if fast else "#" + ".".join(str(i) for i in pid if i != NO_ID))
        found.setdefault(orig.name, []).append(Emitter(label, orig, parent, pid, fast, entries))
    warnings = []
    chosen = []
    for name, ems in sorted(found.items()):
        if limit and len(ems) > limit:
            dist = closest_approach(scene, ems, sample_frames, scale)
            keep = sorted(np.argsort(dist)[:limit])
            warnings.append(f"{len(ems)} instances of tagged object {name}; kept the {limit} closest to the camera "
                            "(scene setting instance_limit)")
            ems = [ems[i] for i in keep]
        chosen += sorted(ems, key=lambda e: e.label)
    return chosen, warnings


def instance_lookup(depsgraph, keys: set) -> dict:
    """World matrices of the requested geometry-nodes instances at the current frame."""
    out, parents = {}, {k[0] for k in keys}
    for inst in depsgraph.object_instances:
        if inst.is_instance and inst.parent is not None and inst.parent.original.name in parents:
            key = instance_key(inst)
            if key in keys:
                out[key] = inst.matrix_world.copy()
    return out


def closest_approach(scene, ems: list[Emitter], sample_frames: list[float], scale: float) -> np.ndarray:
    keys = {(e.instancer.name, e.pid) for e in ems if not e.fast}
    best = np.full(len(ems), np.inf)
    for f in sample_frames:
        util.set_frame(scene, f)
        dg = bpy.context.evaluated_depsgraph_get()
        cam = scene.camera.evaluated_get(dg).matrix_world.translation if scene.camera else None
        if cam is None:
            continue
        lookup = instance_lookup(dg, keys) if keys else None
        for i, e in enumerate(ems):
            d = (e.matrix(dg, lookup).translation - cam).length * scale
            best[i] = min(best[i], d)
    return best


def sample_frames(frame_start: int, frame_end: int, count: int = 30) -> list[float]:
    return [float(f) for f in np.unique(np.round(np.linspace(frame_start, frame_end, count)))]
