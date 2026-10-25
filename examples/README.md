# examples

Script-built example scenes that show how generator scripts tag sounds. Each example is a Python
script run inside Blender that builds the scene from scratch, tags it, and can be baked and
rendered with the commands in [docs/usage.md](../docs/usage.md).

Planned:

- `flyby.py`: one ship passing the camera (engine loop, whoosh one-shot) — the minimal example.
- `station_interior.py`: ambience bed, machinery loops with cones, doors as one-shots, occlusion
  by walls.
- `fleet.py`: many engines at distance, Doppler and air absorption, camera cuts.
