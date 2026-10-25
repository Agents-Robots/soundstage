"""Render report and debug plot.

- Metrics: sample peak, true peak (4x oversampling), integrated loudness and loudness range
  (pyloudnorm, ITU-R BS.1770).
- Per source: active intervals, distance range, playback-rate range, peak contribution, audible
  frames, warnings.
- ``<mix>.report.json`` (format in docs/spec/cli.md) and ``<mix>.plot.png`` (distance, gain, pan,
  delay, pitch per source over a frame axis; matplotlib, optional extra ``plot``).

The report is how agents verify renders without listening (NFR-6). Phase 1 (basic), Phase 3 (full).
"""
