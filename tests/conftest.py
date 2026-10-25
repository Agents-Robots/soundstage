"""Shared fixtures (planned).

- ``tmp_scene``: build a scene file in a temp dir from a manifest dict and arrays
  (static listener at the origin looking down -Z, sources on given trajectories).
- ``sine_sample`` / ``click_sample`` / ``noise_sample``: generated test samples at various rates.
- ``measure``: helpers for RMS level in dB, channel balance, onset sample, dominant frequency in a
  window, maximum sample-to-sample step.
- Skip ``blender``-marked tests when no ``blender`` binary is on PATH.
"""
