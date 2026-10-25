"""Delay, Doppler, ITD (Phase 2).

- Static source at 343 m: impulse arrives 1.000 s later (+/- 1 sample).
- Source passing a static camera at 34.3 m/s with a 1 kHz sine: 1111 Hz approaching, 909 Hz
  receding (+/- 0.5 %), measured far from closest approach.
- Camera passing a static source at 34.3 m/s: 1100 Hz / 900 Hz.
- doppler_factor 0: constant delay, no frequency change; 2: doubled delay variation.
- sync_to_picture: one-shot onset exactly at its frame regardless of distance.
- ITD at 90 degrees = 0.656 ms * itd_scale.
- Near-supersonic source: rate clamped to [0.25, 4], warning emitted, no NaN or crash.
- Cubic and sinc kernels match their numpy references.
"""
