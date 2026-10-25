# 0001. Standalone engine fed by a headless Blender bake

- Status: Accepted
- Date: 2026-10-25
- Ticket: —

## Context

Sound has to follow what the camera sees: source and camera positions over time, camera switches,
and later the geometry for occlusion. All of this is defined in Blender, by generator scripts,
and evaluated by the depsgraph (parenting, constraints, drivers, animation). The DSP (delay lines,
time-varying filters, convolution, loudness metering) needs numpy, scipy and numba, fast
iteration, and tests that do not start Blender.

Blender already contains a 3D audio engine (audaspace: Speaker objects, Doppler, distance models,
mixdown to a file).

## Decision

Split the work in two:

1. **Bake** (`soundstage/blender/bake.py`), run with `blender -b --factory-startup --python`:
   evaluates the scene frame by frame and writes listener and source trajectories, settings and
   resolved tags to a scene file.
2. **Engine** (`soundstage/engine/`), a normal Python package in its own venv: reads the scene
   file and renders the audio.

Blender's built-in speaker mixdown is used only as a baseline in Phase 0 and as an alternative
way to declare sources (Speaker objects, FR-8), not for rendering.

## Alternatives considered

- **Blender Speaker objects plus mixdown**: no code to write for the minimum requirements, but
  amplitude panning only, Doppler as a pitch effect without propagation delay, no air absorption,
  occlusion, reverb or stems, no insight into what it computed, and headless mixdown is poorly
  documented. Extending audaspace means C++ in Blender's source.
- **The whole engine inside Blender's Python**: possible (Blender ships numpy), but scipy, soxr,
  numba and soundfile are not available there without installing into Blender's Python, every
  render reloads the scene, and tests need Blender.
- **Exporting from Blender to a game engine or middleware** (Unity, Unreal, FMOD, Steam Audio):
  real-time engines, no frame-exact offline output without large glue code.

## Consequences

- Re-rendering with different settings (Doppler strength, solo a source) does not touch Blender.
- The scene file is a contract that must be versioned and documented (ADR
  [0004](0004-scene-interchange-json-npz.md)).
- Two runtime environments: Blender's Python for `soundstage/blender/` (bpy and Blender's numpy
  only) and the venv for the engine. The package root must not import engine dependencies.
- Anything that needs scene geometry at render time (occlusion, later reflections) has to be
  precomputed in the bake.
