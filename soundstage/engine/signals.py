"""Samples and dry timelines.

- Decode samples with soundfile (WAV, FLAC, OGG), cache per path; downmix spatial sources to mono,
  keep beds stereo.
- Resample to the output rate with soxr; apply ``pitch`` as an extra ratio.
- Build each source's dry signal over emission time, covering the pre-roll and the longest delay:
  loops tiled with an equal-power seam crossfade and a seeded start phase, one-shots placed at their
  trigger time, raised-cosine fades.

Spec: docs/spec/signal-model.md#dry-timeline. Phase 1.
"""
