"""Tag helper for scene generator scripts: attach sounds to Blender objects.

Writes plain data into custom properties, so tags are saved in the .blend, visible in Object
Properties -> Custom Properties, and readable without an add-on (ADR 0003). Only the keys given
are stored; defaults are filled in at bake time from ``schema``.

    from soundstage.blender import tag
    tag.add_sound(ship, "engine_hum.wav", gain_db=-6, ref_distance=20, group="engines")
    tag.add_sound(door, "door_slam.wav", mode="once", frame=240)

Imports only bpy and the standard library. Spec: docs/spec/tagging.md.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import bpy

from . import schema

PROP = "sfx"
SETTINGS_PROP = "sfx_settings"


def _plain(value):
    """Convert ID property values (groups, arrays) to plain Python data."""
    if hasattr(value, "to_dict"):
        return {k: _plain(v) for k, v in value.to_dict().items()}
    if hasattr(value, "to_list"):
        return value.to_list()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def get_sounds(obj) -> list[dict]:
    """The object's tag entries as plain dicts (also accepts a JSON string in the property)."""
    raw = obj.get(PROP)
    if raw is None:
        return []
    if isinstance(raw, str):
        return json.loads(raw)
    return [_plain(e) for e in raw]


def add_sound(obj, sample: str, *, mode: str = "loop", frame=None, **params) -> dict:
    """Validate and append a sound entry to ``obj["sfx"]``; return the entry.

    For one-shots ``frame`` may be a list of frames (one sound, triggered at each frame).
    Raises ``ValueError`` listing every problem if a parameter is invalid.
    """
    entry = {"sample": sample, "mode": mode, **params}
    if isinstance(frame, (list, tuple, range)):
        entry["frame"] = [float(f) for f in frame]
    elif frame is not None:
        entry["frame"] = float(frame)
    for key in ("offset", "variants"):
        if isinstance(entry.get(key), tuple):
            entry[key] = list(entry[key])
    errors = schema.validate_source(entry)
    if errors:
        raise ValueError(f"{obj.name}: " + "; ".join(errors))
    obj[PROP] = get_sounds(obj) + [entry]
    return entry


def clear_sounds(obj) -> None:
    """Remove all sound tags from an object."""
    if PROP in obj:
        del obj[PROP]


def get_scene_settings(scene=None) -> dict:
    scene = scene or bpy.context.scene
    raw = scene.get(SETTINGS_PROP)
    if raw is None:
        return {}
    return json.loads(raw) if isinstance(raw, str) else _plain(raw)


def set_scene_settings(scene=None, **settings) -> dict:
    """Validate and merge settings into ``scene["sfx_settings"]``; return the merged dict."""
    scene = scene or bpy.context.scene
    merged = {**get_scene_settings(scene), **settings}
    errors = schema.validate_settings(merged)
    if errors:
        raise ValueError(f"scene {scene.name}: " + "; ".join(errors))
    scene[SETTINGS_PROP] = merged
    return merged


def iter_tagged(scene=None) -> Iterator[tuple[object, int, dict]]:
    """All (object, index, entry) triples of tagged objects in the scene, sorted by object name."""
    scene = scene or bpy.context.scene
    for obj in sorted(scene.objects, key=lambda o: o.name):
        for i, entry in enumerate(get_sounds(obj)):
            yield obj, i, entry
