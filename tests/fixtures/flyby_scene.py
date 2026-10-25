"""Script-built test scene: a flyby past a moving camera (runs inside Blender).

Planned content:

- Empty scene, 30 fps, frames 1-300, scale_length 1.
- Camera moving slowly along +Y, looking along +Y.
- Emitter "Flyer" crossing from left to right in front of the camera at a known speed and closest
  distance, tagged with a sine loop (Doppler and pan checks).
- Emitter "Impact" static at a known distance, tagged with a click one-shot at frame 120 (onset
  and delay checks).
- A second camera bound by a marker at frame 200 (cut handling, Phase 2).
- An occluder plane passing between camera and "Flyer" (Phase 3).

Run: ``blender -b --factory-startup -y --python tests/fixtures/flyby_scene.py -- --save <path.blend>``.
"""
