"""Propagation: retarded time, delay, Doppler, ITD, fractional-delay reads.

- Solve the retarded time ``tau = |s(t - tau) - p(t)| / c`` by fixed-point iteration at control rate.
- Derive read delays: Doppler factor around the start delay, ``sync_to_picture`` for one-shots,
  Woodworth ITD offsets per ear.
- Clamp the playback rate to [0.25, 4] and report where it applies.
- Upsample delays to audio rate; read the dry signal at fractional positions (cubic Hermite, or
  Kaiser-windowed sinc with anti-aliasing for ``quality="high"``) in numba kernels with numpy
  reference versions.

Spec: docs/spec/signal-model.md#propagation-delay-doppler-itd; decision: ADR 0006. Phase 2.
"""
