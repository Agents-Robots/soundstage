"""End to end with Blender (marker ``blender``).

- Build ``fixtures/flyby_scene.py`` headless, bake, render.
- The one-shot's onset in the WAV is at t(frame) + d/c (or t(frame) with sync_to_picture).
- Pan goes from left to right during the flyby; playback rate > 1 before and < 1 after the closest
  approach (Phase 2).
- Tags survive save and reload of the .blend.
"""
