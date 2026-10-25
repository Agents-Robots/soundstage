# Guide for agents that build scenes: sound from the start

For a coding agent (or a person) whose scripts build Blender scenes from scratch: how to write them
so that the scene has its sound as soon as it is built, and keeps it when it is rebuilt. Adding
sound to an animation that already exists is the [agent guide](agent-guide.md).

The idea: the script that creates an object also says what it sounds like. Sound is part of the
asset, like its material.

## 1. Import the tag helper

```python
import sys
sys.path.insert(0, "/path/to/soundstage")      # the soundstage checkout
from soundstage.blender import tag              # bpy and stdlib only; nothing to install in Blender
```

Keep the path in one place (a project config or an environment variable read by the build script).

## 2. Scale, names, cameras

- **1 Blender unit = 1 metre** (or set `scene.unit_settings.scale_length`; the bake converts).
  Distances, speeds and the Doppler effect depend on it.
- **Stable ids**: a source's id defaults to `"<object name>:<index>"`. If names are generated
  (`Car.017`), pass `id="car_hero_engine"` for the sources you will refer to (solo, mute, reports);
  ids also seed loop phases, so a stable id keeps the render reproducible.
- The **active camera** is the listener; camera switches (markers bound to cameras) become cuts.
  A camera rig whose camera object is parented to an empty works as is.

## 3. Tag assets where they are made

```python
def build_car(name, collection):
    body = make_car_mesh(name, collection)
    engine = bpy.data.objects.new(f"{name}_engine", None)      # an empty at the engine
    engine.parent = body
    engine.location = (0, -1.6, 0.4)
    collection.objects.link(engine)
    tag.add_sound(engine, "car_engine_loop.wav", gain_db=-6, ref_distance=4, group="traffic",
                  loop_phase="random")
    return body
```

- **Emitter position**: put the tag on the object, or on an empty parented to it, or use `offset`
  (object-local metres). Keep the emitter **inside** the object's bounding box: the object then
  never occludes its own sound (an emitter outside, e.g. at the tip of a long nozzle, is shadowed by
  the body from the far side, as in reality).
- **Instanced assets**: tag the object inside the asset collection once. Every collection instance
  and geometry-nodes instance of it becomes a source, the 32 closest to the camera by default
  (`tag.set_scene_settings(instance_limit=...)`). A city with 500 instanced cars thus renders the
  engines that matter.
- **One-shots** belong to the code that animates the event: when the script keyframes a door to
  open at frame 240, it adds `tag.add_sound(door, "door_open.wav", mode="once", frame=240)` in the
  same place. Repeating events take a list of frames.
- **Beds** (room tone, wind, music): `spatial=False`, on any object (a scene root empty),
  `group="ambience"`.
- **Groups** become stems: use a few meaningful ones (`engines`, `traffic`, `crowd`, `sfx`,
  `ambience`, `music`) so the stems are useful in Fairlight.

## 4. Mark what sound should pass through

Every rendered mesh of 2 m or more occludes by its bounding box, a merged mesh by the boxes of its
parts. Fog and
light volumes, light beams and holograms (light-only materials), the camera's own vehicle and the
ground under a source are left out automatically; glass blocks. Set `sfx_occluder` where a box is
wrong, in the code that makes the object:

```python
fence["sfx_occluder"] = False                                # foliage, fences, nets, open structures
archway["sfx_occluder"] = "mesh"                             # a part with an opening: real triangles
bpy.data.collections["Trees"]["sfx_occluder"] = False        # for every instance of an asset
```

Merged meshes are fine as long as their parts are separate islands (a district of buildings in one
mesh gives one box per building); a single connected part that wraps around open space (a ring of
brackets joined by a band, a courtyard building) needs `"mesh"`. Hidden helper geometry that still
renders (proxies, colliders) should be `hide_render = True` or `sfx_occluder = False`.

## 5. Scene settings

```python
tag.set_scene_settings(
    samples_root="//audio/samples/",      # relative sample paths resolve here (// = next to the .blend)
    reverb="city_streets",                # an EFX preset (soundstage presets) or an IR file
    doppler_factor=1.0,                   # 0 off, 1 physical, >1 exaggerated
)
```

Everything else has documented defaults ([spec/tagging.md](spec/tagging.md)). Reverb, occlusion
strength and Doppler can also be changed at render time with `--set`, without rebuilding.

## 6. Build, bake, render, check

```bash
blender -b --factory-startup --python scripts/build.py -- --save shot.blend    # however the project builds
soundstage bake shot.blend --out audio/bake/shot                                  # or --run scripts/build.py
soundstage render audio/bake/shot/scene.json -o audio/out/shot.wav --report --plot
```

Check the report and the plot as in the [agent guide](agent-guide.md#7-verify-you-cannot-listen):
every featured source audible, distances and playback rates plausible, visibility dropping only
where the picture hides a source.

## 7. Rules

- Tags live in the build scripts (or a tagging script run with `bake --run`), never only in a saved
  .blend: a rebuilt scene must come back with its sound (NFR-1).
- Samples: mono for spatial sources, trimmed to the onset for one-shots, licence noted in the
  project; any sample rate.
- Do not bake sound into the scene in other ways (Blender sequencer strips, baked audio): the bake
  reads tags, Speaker objects and instances only.
- Hand-placed Speaker objects are fine too and are read the same way; a scene can mix both.
