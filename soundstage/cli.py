"""Command-line entry point ``soundstage`` with the subcommands bake, inspect, render, preview.

- ``bake``: builds the ``blender -b <blend> --factory-startup -y --python soundstage/blender/bake.py -- ...``
  command line, runs it and checks that scene.json and scene.npz were written.
- ``inspect``: summarizes a scene file (sources, distance and speed ranges, cuts, warnings).
- ``render``: loads a scene file, applies ``--set`` overrides, runs ``engine.render`` and writes
  the mix, stems, report and plot.
- ``preview``: muxes a mix with a frame sequence or video into an MP4 via ffmpeg.

Arguments, exit codes and report format: docs/spec/cli.md. Phase 1 (bake, inspect, render,
preview), later phases add options.
"""
