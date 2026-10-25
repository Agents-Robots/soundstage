"""Load, validate and represent a scene file (scene.json + scene.npz).

- Check ``format`` and ``version``; refuse unknown versions (ADR 0004).
- Apply ``--set`` overrides to the scene settings and validate them with ``blender.schema``.
- Build dataclasses: ``Scene`` (time base, settings, listener arrays, cuts, sources),
  ``Source`` (resolved tag parameters, track index), ``Settings``.
- Time helpers: frame -> seconds -> samples with ``fps / fps_base`` (exact for 29.97).
- ``write_scene(path, manifest, arrays)`` for tests and hand-made scenes without Blender.

Spec: docs/spec/scene-format.md. Phase 1.
"""
