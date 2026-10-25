"""Samples and dry timelines (Phase 1).

- Any input rate (22.05, 44.1, 96 kHz) is resampled to 48 kHz with correct duration.
- Stereo spatial sample is downmixed; stereo bed stays stereo; mono bed is -3.01 dB per channel.
- One-shot starts exactly at its trigger sample.
- Loop seam: no step larger than the signal's own maximum step; equal-power crossfade keeps level.
- Seeded loop phase: same source id -> same phase; different ids -> different phases.
- Fades are raised-cosine and reach exactly 0 / 1.
"""
