"""Time-varying filters (Phase 2, Phase 3).

- One-pole low-pass: -3 dB at the set cutoff (static), state carried across chunks gives the same
  output as one long run.
- Air absorption cutoffs: 13.9 kHz at 10 m, 4.4 kHz at 100 m, 1.4 kHz at 1 km (air_absorption 1).
- Head shadow: flat at head_shadow 0; near-ear treble boost and far-ear cut at 90 degrees.
- Occlusion: fully occluded -> occlusion_gain_db and cutoff; transitions without steps.
- Kernels match numpy references on random input and random coefficient trajectories.
"""
