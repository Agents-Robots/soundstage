"""Scene file loading and time base (Phase 1).

- Round trip ``write_scene`` -> load gives equal manifest and arrays.
- Unknown ``version`` is rejected.
- ``--set`` overrides are applied and validated.
- Frame -> sample mapping: frame 120 at 30 fps, frame_start 1 -> sample 190400; exact for 29.97 and
  23.976 (fps_base 1.001); output length for 24, 25, 30, 29.97 fps.
"""
