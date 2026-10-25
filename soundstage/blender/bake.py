"""Bake a Blender shot into a scene file (scene.json + scene.npz) for the engine.

Run headless::

    blender -b shot.blend --factory-startup -y --python soundstage/blender/bake.py -- \
        --out audio/bake/shot1 [--frames A-B] [--scene NAME] [--substeps N] [--pad SECONDS] \
        [--run build.py ...] [--skip-invalid]

Steps:

1. Optionally run generator scripts (``--run``) so the scene is rebuilt from scripts (NFR-1).
2. Collect and validate tags (``tag.iter_tagged``, ``schema.validate_source``); resolve sample
   paths (``//`` relative to the .blend, bare paths against ``samples_root``) and defaults.
3. Step through frames and sub-frames over the shot plus padding (``scene.frame_set(f, subframe=s)``);
   read evaluated world matrices from the depsgraph: listener (active camera per frame, or the
   ``listener`` setting), each emitter (object matrix applied to the tag's ``offset``), forward axis.
4. Detect cuts: camera switches and listener or source jumps above a speed threshold.
5. Ray-cast visibility from the listener to each emitter (Phase 3).
6. Apply ``unit_settings.scale_length`` and write the scene file (docs/spec/scene-format.md).

Uses bpy, stdlib and Blender's bundled numpy only. Phase 1 (per frame), Phase 2 (sub-frames,
padding, cuts, forward vectors, offsets), Phase 3 (visibility, Speaker objects, instances).
"""
