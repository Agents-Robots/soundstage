"""Schema of sound tags (``obj["sfx"]`` entries) and scene settings (``scene["sfx_settings"]``).

The single source of defaults (NFR-8): every key with its kind, default, allowed values or range,
and the phase that implements it. Used by ``tag.add_sound`` for validation, by ``bake`` to resolve
defaults into the scene file, and by the engine for ``--set`` overrides and for scene files written
without Blender.

Stdlib only (no bpy, no numpy), so both Blender and the venv can import it.
Meaning of each key: docs/spec/tagging.md and docs/spec/signal-model.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

REQUIRED = object()
"""Default marker for keys that must be given."""


@dataclass(frozen=True)
class Field:
    kind: str  # "str", "float", "bool", "int", "vec3", "phase", "str_list", "choice", "frames"
    default: object
    choices: tuple[str, ...] | None = None
    min: float | None = None
    max: float | None = None
    nullable: bool = False
    phase: int = 1


AXES = ("X", "-X", "Y", "-Y", "Z", "-Z")
# Model names; the engine's registries must offer the same names (tests/test_models.py).
DISTANCE_MODELS = ("inverse_clamped", "linear_clamped", "exponential_clamped", "none")
PANNERS = ("amplitude", "hybrid")
PAN_LAWS = ("sine", "power")
QUALITIES = ("standard", "high")
OCCLUSION_MODES = ("obstruction", "occlusion")

SOURCE_KEYS: dict[str, Field] = {
    "sample": Field("str", REQUIRED),
    "id": Field("str", None, nullable=True),
    "mode": Field("choice", "loop", choices=("loop", "once")),
    "frame": Field("frames", None, nullable=True),  # one-shots: a frame or a list of frames
    "end_frame": Field("float", None, nullable=True),
    "fade_in": Field("float", None, min=0.0, nullable=True),  # None: 0 (once), 0.05 (loop with frame)
    "fade_out": Field("float", 0.05, min=0.0),
    "loop_phase": Field("phase", "random"),
    "loop_crossfade": Field("float", 0.05, min=0.0),
    "gain_db": Field("float", 0.0, max=60.0),
    "pitch": Field("float", 1.0, min=0.01, max=100.0),
    "group": Field("str", "sfx"),
    "spatial": Field("bool", True),
    "distance_model": Field("choice", "inverse_clamped", choices=DISTANCE_MODELS),
    "ref_distance": Field("float", 1.0, min=1e-6),
    "max_distance": Field("float", None, min=1e-6, nullable=True),
    "rolloff": Field("float", 1.0, min=0.0),
    "offset": Field("vec3", (0.0, 0.0, 0.0)),
    "forward_axis": Field("choice", "-Z", choices=AXES, phase=2),
    "cone_inner_deg": Field("float", 360.0, min=0.0, max=360.0, phase=2),
    "cone_outer_deg": Field("float", 360.0, min=0.0, max=360.0, phase=2),
    "cone_outer_gain_db": Field("float", -12.0, phase=2),
    "doppler": Field("float", 1.0, min=0.0, phase=2),
    "air_absorption": Field("float", 1.0, min=0.0, phase=2),
    "sync_to_picture": Field("bool", False, phase=2),
    "occlusion": Field("bool", True, phase=3),
    "occlusion_radius": Field("float", 0.25, min=0.0, phase=3),  # source size: least Fresnel radius
    "occlusion_mode": Field("choice", "obstruction", choices=OCCLUSION_MODES, phase=3),
    "reverb_send_db": Field("float", None, nullable=True, phase=3),  # None: 0 dB spatial, no send for beds
    "variants": Field("str_list", (), phase=4),
    "gain_jitter_db": Field("float", 0.0, min=0.0, phase=4),
    "pitch_jitter": Field("float", 0.0, min=0.0, phase=4),
    "gain_prop": Field("str", None, nullable=True, phase=4),
    "pitch_prop": Field("str", None, nullable=True, phase=4),
}

SCENE_SETTINGS: dict[str, Field] = {
    "samples_root": Field("str", "//audio/samples/"),
    "sample_rate": Field("int", 48000, min=8000, max=384000),
    "speed_of_sound": Field("float", 343.0, min=1.0, phase=2),
    "doppler_factor": Field("float", 1.0, min=0.0, phase=2),
    "air_absorption": Field("float", 1.0, min=0.0, phase=2),
    "air_temperature_c": Field("float", 20.0, min=-50.0, max=60.0, phase=2),
    "air_humidity_pct": Field("float", 50.0, min=0.0, max=100.0, phase=2),
    "teleport_speed": Field("float", None, min=1.0, nullable=True, phase=2),  # None: 3 x speed_of_sound
    "panner": Field("choice", "hybrid", choices=PANNERS),
    "pan_law": Field("choice", "sine", choices=PAN_LAWS, phase=2),
    "itd_scale": Field("float", 0.5, min=0.0, max=1.0, phase=2),
    "head_shadow": Field("float", 0.5, min=0.0, max=1.0, phase=2),
    "head_radius": Field("float", 0.0875, min=0.01, max=1.0, phase=2),
    "rear_cutoff_hz": Field("float", 6000.0, min=20.0, max=20000.0, phase=2),
    "rear_gain_db": Field("float", -2.0, phase=2),
    "master_gain_db": Field("float", 0.0),
    "substeps": Field("int", 4, min=1, max=64),
    "pad_seconds": Field("float", 3.0, min=0.0),
    "listener": Field("str", None, nullable=True),
    "quality": Field("choice", "standard", choices=QUALITIES, phase=2),
    "occlusion_gain_db": Field("float", -12.0, phase=3),
    "occlusion_cutoff_hz": Field("float", 1500.0, min=20.0, max=20000.0, phase=3),
    "reverb": Field("str", None, nullable=True, phase=3),  # EFX preset name or impulse-response file
    "reverb_send_db": Field("float", 0.0, phase=3),
    "reverb_room_rolloff": Field("float", None, min=0.0, nullable=True, phase=3),  # None: the preset's
    "read_speakers": Field("bool", True, phase=3),
    "occlusion_rate": Field("float", 10.0, min=0.0, phase=3),  # visibility samples per second; 0: none
    "occluder_min_size": Field("float", 2.0, min=0.0, phase=3),  # m: smaller objects do not occlude
    "instance_limit": Field("int", 32, min=0, phase=3),
}

IMPLEMENTED_PHASE = 3
"""Keys with a higher phase are validated and stored, but the engine ignores them (with a warning)."""

BAKE_SETTINGS = ("samples_root", "substeps", "pad_seconds", "listener", "read_speakers", "occlusion_rate",
                 "occluder_min_size", "instance_limit")
"""Scene settings used only by the bake; overriding them at render time changes nothing."""


def _is_number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _check(key: str, field: Field, value: object) -> str | None:
    """Return an error message for one value, or None if valid."""
    if value is None:
        return None if field.nullable else f"{key}: must not be null"
    kind = field.kind
    if kind == "str" and not isinstance(value, str):
        return f"{key}: expected a string, got {value!r}"
    if kind == "bool" and not isinstance(value, bool):
        return f"{key}: expected true/false, got {value!r}"
    if kind == "choice" and value not in field.choices:
        return f"{key}: {value!r} is not one of {', '.join(field.choices)}"
    if kind in ("float", "int"):
        if not _is_number(value):
            return f"{key}: expected a number, got {value!r}"
        if kind == "int" and int(value) != value:
            return f"{key}: expected an integer, got {value!r}"
        if field.min is not None and value < field.min:
            return f"{key}: {value} is below the minimum {field.min}"
        if field.max is not None and value > field.max:
            return f"{key}: {value} is above the maximum {field.max}"
    if kind == "vec3":
        if not (isinstance(value, (list, tuple)) and len(value) == 3 and all(_is_number(c) for c in value)):
            return f"{key}: expected three numbers [x, y, z], got {value!r}"
    if kind == "phase":
        if not (value == "random" or (_is_number(value) and value >= 0)):
            return f"{key}: expected \"random\" or seconds >= 0, got {value!r}"
    if kind == "frames":
        if not (_is_number(value) or (isinstance(value, (list, tuple)) and value and all(_is_number(c) for c in value))):
            return f"{key}: expected a frame number or a non-empty list of frame numbers, got {value!r}"
    if kind == "str_list":
        if not (isinstance(value, (list, tuple)) and all(isinstance(s, str) for s in value)):
            return f"{key}: expected a list of strings, got {value!r}"
    return None


def _validate(entry: dict, fields: dict[str, Field]) -> list[str]:
    errors = [f"unknown key {k!r}" for k in entry if k not in fields]
    for key, field in fields.items():
        if key in entry:
            msg = _check(key, field, entry[key])
            if msg:
                errors.append(msg)
        elif field.default is REQUIRED:
            errors.append(f"{key}: required")
    return errors


def validate_source(entry: dict) -> list[str]:
    """Error messages for one tag entry, empty if valid."""
    errors = _validate(entry, SOURCE_KEYS)
    if errors:
        return errors
    if entry.get("mode", "loop") == "once" and entry.get("frame") is None:
        errors.append("frame: required for mode 'once'")
    if entry.get("distance_model") == "linear_clamped" and entry.get("max_distance") is None:
        errors.append("max_distance: required for distance_model 'linear_clamped'")
    if entry.get("max_distance") is not None and entry["max_distance"] < entry.get("ref_distance", 1.0):
        errors.append("max_distance: must not be smaller than ref_distance")
    frame = entry.get("frame")
    if isinstance(frame, (list, tuple)) and entry.get("mode", "loop") == "loop":
        errors.append("frame: a list of frames is only allowed for mode 'once'")
    elif entry.get("end_frame") is not None and frame is not None and entry["end_frame"] < frame:
        errors.append("end_frame: must not be before frame")
    return errors


def resolve_source(entry: dict, default_id: str | None = None) -> dict:
    """Entry with every key filled in. The entry must be valid."""
    out = {}
    for key, field in SOURCE_KEYS.items():
        value = entry.get(key, field.default)
        if isinstance(value, tuple):
            value = list(value)
        out[key] = value
    out["offset"] = [float(c) for c in out["offset"]]
    if isinstance(out["frame"], (list, tuple)):
        out["frame"] = sorted(float(f) for f in out["frame"])
    if out["id"] is None:
        out["id"] = default_id
    if out["fade_in"] is None:
        out["fade_in"] = 0.05 if (out["mode"] == "loop" and out["frame"] is not None) else 0.0
    return out


def validate_settings(settings: dict) -> list[str]:
    """Error messages for scene settings, empty if valid."""
    return _validate(settings, SCENE_SETTINGS)


def resolve_settings(settings: dict) -> dict:
    """Scene settings with every key filled in. The settings must be valid."""
    return {key: settings.get(key, field.default) for key, field in SCENE_SETTINGS.items()}


def unimplemented(entry: dict, fields: dict[str, Field]) -> list[str]:
    """Keys set to a non-default value that the engine does not implement yet."""
    return [
        key
        for key, field in fields.items()
        if field.phase > IMPLEMENTED_PHASE and key in entry and entry[key] != field.default
        and not (isinstance(field.default, tuple) and list(field.default) == entry[key])
    ]


def parse_value(key: str, text: str, fields: dict[str, Field] = SCENE_SETTINGS) -> object:
    """Parse a command-line ``key=value`` value into the key's kind."""
    if key not in fields:
        raise ValueError(f"unknown setting {key!r}")
    field = fields[key]
    if text.lower() in ("null", "none") and field.nullable:
        return None
    if field.kind == "float":
        return float(text)
    if field.kind == "int":
        return int(text)
    if field.kind == "bool":
        if text.lower() not in ("true", "false", "1", "0", "yes", "no"):
            raise ValueError(f"{key}: expected true/false, got {text!r}")
        return text.lower() in ("true", "1", "yes")
    return text
