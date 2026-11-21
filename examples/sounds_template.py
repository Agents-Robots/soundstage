"""Tagging script template: add sounds to an existing animation (runs inside Blender at bake time).

Copy this file next to the animation (e.g. <project>/audio/sounds.py), fill in the SOUNDS table,
then:

    soundstage bake <project>/shot.blend --run <project>/audio/sounds.py --out <project>/audio/bake/shot
    soundstage render <project>/audio/bake/shot/scene.json -o <project>/audio/out/shot.wav --report --plot

The .blend is not modified: the tags exist only in the bake. Re-running gives the same result,
because old tags are cleared first. Parameters: docs/spec/tagging.md.
"""

import sys
from pathlib import Path

import bpy

SOUNDSTAGE = "/path/to/soundstage"  # `soundstage blender-path`; only for running outside bake --run
SAMPLES = Path(__file__).resolve().parent / "samples"  # folder with the WAV/FLAC/OGG files

sys.path.insert(0, SOUNDSTAGE)
from soundstage.blender import tag  # noqa: E402

# (object name, sample file, parameters). Object names come from `soundstage scan`.
SOUNDS = [
    # A moving vehicle: engine loop, audible from far away.
    # ("Ship", "engine_hum.wav", dict(gain_db=-6, ref_distance=20, group="engines")),
    # An event: one-shot at the frame where it happens on screen.
    # ("Crate", "impact.wav", dict(mode="once", frame=180, ref_distance=5)),
    # A repeating event: a list of frames.
    # ("Beacon", "beep.wav", dict(mode="once", frame=list(range(1, 241, 30)), ref_distance=3)),
    # Ambience bed on any object (position ignored).
    # ("Camera", "room_tone.wav", dict(spatial=False, gain_db=-20, group="ambience")),
]

# Environment: one reverb preset for the shot (`soundstage presets` lists them), or None.
REVERB = None  # e.g. "city_streets", "hangar", "forest", "spacestation_hall"

# Occluders whose boxes are wrong: open objects (foliage, fences, nets, scaffolding): False; parts
# with openings (arches, courtyard buildings): "mesh". Collection names work too and
# cover every instance of that collection. Fog, light beams and the camera's vehicle are left out
# automatically; glass blocks.
OCCLUDERS = {
    # "Fence": False,
    # "Trees": False,          # a collection
    # "Archway": "mesh",
}

scene = bpy.context.scene
for obj in scene.objects:
    tag.clear_sounds(obj)
tag.set_scene_settings(samples_root=str(SAMPLES) + "/", reverb=REVERB)
for name, mode in OCCLUDERS.items():
    target = bpy.data.objects.get(name) or bpy.data.collections.get(name)
    if target is None:
        raise SystemExit(f"occluder {name!r}: no object or collection of that name")
    target["sfx_occluder"] = mode

missing = [name for name, _, _ in SOUNDS if name not in scene.objects]
if missing:
    raise SystemExit(f"objects not found in {bpy.data.filepath}: {', '.join(missing)}")
for name, sample, params in SOUNDS:
    tag.add_sound(scene.objects[name], sample, **params)
