"""Group buses, master and file output.

- Accumulate sources into group buses; master = groups + reverb return, times ``master_gain_db``.
- Optional true-peak limiter and loudness normalization (off by default).
- Trim to the shot (sample 0 = first frame) and write WAV: 32-bit float, or 24-bit PCM with TPDF
  dither; stems as ``<mix>_stem_<group>.wav``.

Spec: docs/spec/signal-model.md#mixing-and-output; decision: ADR 0005. Phase 1 (master),
Phase 3 (stems, limiter, normalization).
"""
