"""Sound tags for the flyby example (runs inside Blender, applied at bake time).

This is the pattern for adding sound to an existing animation: a tagging script next to the
project, applied with ``soundstage bake <blend> --run <this script>``. The .blend itself is not
modified, and re-running the script gives the same tags (it clears old ones first).

    soundstage bake out/flyby.blend --run examples/flyby_sounds.py --out out/flyby
    soundstage render out/flyby/scene.json -o out/flyby/mix.wav --report
"""

import sys
from pathlib import Path

import bpy

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from soundstage.blender import tag  # noqa: E402

scene = bpy.context.scene
objects = scene.objects
for obj in objects:
    tag.clear_sounds(obj)

tag.set_scene_settings(samples_root=str(REPO / "samples") + "/")

# Ship: engine loop all the time, plus a whoosh centred on the closest approach (frame ~120;
# the whoosh is 1.6 s = 48 frames long, so it starts 24 frames earlier).
tag.add_sound(objects["Ship"], "engine_hum.wav", gain_db=-3, ref_distance=15, group="engines")
tag.add_sound(objects["Ship"], "whoosh.wav", mode="once", frame=96, gain_db=-4, ref_distance=15, group="engines")

# Beacon on the left: a beep every second.
tag.add_sound(objects["Beacon"], "beep.wav", mode="once", frame=list(range(1, 241, 30)), gain_db=-6, ref_distance=3)

# Crate hits the ground at frame 180.
tag.add_sound(objects["Crate"], "impact.wav", mode="once", frame=180, ref_distance=5)

# Ambience bed, not placed in space.
tag.add_sound(objects["Ambience"], "ambience_stereo.wav", spatial=False, gain_db=-6, group="ambience")
