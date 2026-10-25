"""Reverb send bus.

- Mono send per spatial source, after the delay read and before panning, with the send's own
  distance law (half the rolloff).
- Impulse responses from a file, or presets synthesized by seed (decorrelated exponentially decaying
  noise with RT60, pre-delay and high-frequency damping), so no licensed files are needed.
- Partitioned FFT convolution per chunk; return written as stem ``reverb``.

Spec: docs/spec/signal-model.md#reverb-send. Phase 3.
"""
