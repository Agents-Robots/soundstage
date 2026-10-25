"""Gain laws, cutoff laws and time-varying filter kernels.

- Gains: distance models (inverse, linear, exponential clamped, none), directivity cone, rear cue,
  occlusion.
- Cutoffs: air absorption by distance, rear cue, occlusion.
- Kernels: time-varying one-pole low-pass and Brown-Duda head-shadow shelf with per-block
  coefficients and state carried across chunks (numba, with numpy references).

Spec: docs/spec/signal-model.md (distance gain, directivity cone, air absorption, rear cue,
occlusion, panning). Phase 1 (distance gain), Phase 2 (the rest), Phase 3 (occlusion).
"""
