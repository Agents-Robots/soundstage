"""Render orchestration.

1. Geometry pass for all sources at control rate: delays, gains, cutoffs, statistics, culling of
   sources inaudible for a whole chunk.
2. Audio pass in chunks (~10 s, with overlap for filter state and delay reach): per source
   fractional-delay read, filter cascade, gains, pan, accumulate into group bus and reverb send.
3. Hand buses to ``mix`` and statistics to ``report``.

Supports frame sub-ranges and solo/mute (FR-67). Data flow: docs/architecture.md#data-flow-inside-a-render.
Phase 1.
"""
