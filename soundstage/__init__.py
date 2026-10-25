"""soundstage: offline spatial sound for script-generated Blender animations.

Two halves share this package and must not import each other's dependencies:

- ``soundstage.blender`` runs inside Blender's Python (bpy and Blender's bundled numpy only).
- ``soundstage.engine`` and ``soundstage.cli`` run in the repo venv (numpy, scipy, soundfile,
  soxr, numba, pyloudnorm), never import bpy.

Keep this module free of third-party imports so Blender can import ``soundstage.blender``.
See docs/architecture.md.
"""
