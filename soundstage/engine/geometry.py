"""Trajectories and listener-relative geometry at control rate.

- Split the baked timeline into segments at listener cuts (and per source at teleports).
- Interpolate positions with cubic splines and listener rotation with quaternion slerp, per segment.
- Evaluate at the control rate (1 kHz): listener pose, source positions, camera-space vectors
  ``q = R^T (s - p)``, softened distance, lateral sine and angle, rear factor, cone angle.

Phase 1 uses frame-rate samples with linear interpolation and no retarded time. Spec:
docs/spec/signal-model.md#coordinate-frames, #trajectories-and-control-rate. Phase 2.
"""
