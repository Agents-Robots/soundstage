# 0013. Two render tiers: the full chain for the loudest sources, a far field for the rest

- Status: Accepted
- Date: 2026-10-30
- Ticket: #31, #32

## Context

Shots with thousands of sources (flying traffic, fleets, crowds) did not fit: every source ran the
full chain of ADR 0009 and held about 21–27 MB of whole-shot arrays, so 5000 sources did not fit in
110 GB (E16). Culling (FR-68) skips only what is negligible against the rest of its group, and
sources that fill an area contribute a similar power share from every octave of distance, so it
skips few of them (E16). No professional system renders thousands of sources individually at full
detail; they keep the near, loud ones individual and render the rest as aggregates
(`research/survey.md#many-sources`).

## Decision

**Two tiers per source and 4 s chunk.** Per group, the `detail_voices` sources (default 64) with the
most estimated energy in a chunk run the full chain (the near tier); the others run the far field
(`engine/farfield.py`). The estimate is the culling estimate from the baked positions, so tiers are
assigned before any setup. A tier change crossfades both renders over 100 ms with a law for their
expected correlation.

**The far field is per-source in time and direction, shared in filtering.** Each far voice reads
its dry signal from a buffer shared by all voices of the same sample, with pitch, Doppler and the
travel delay in the read position, and adds it with its gains and amplitude pan into per-group
buses: distance bands × open / occluded. Each bus is filtered once (air absorption of its band
distance; transmission low-pass for the occluded ones). A voice's weight is split between the two
bands around its distance and by its visibility, so nothing switches. Its geometry is computed per
chunk from the baked positions; nothing is kept per voice over the whole shot.

**The bake follows the tiers.** At every visibility sample the bake ranks the sources of each
group by the same estimate; those beyond 2 × `detail_voices` get the direct path only instead of
the 13 paths of the Fresnel rings.

**Near renderers live for their run of near chunks only** (on a part of the control grid), so
render memory follows the near voices alive at a time.

## Alternatives considered

- **Clustering by direction** (Tsingos et al. 2004, Atmos spatial coding): premix the far sources
  into a few clusters and render each cluster as one source. In stereo the direction costs two
  multiplies per sample, so it stays per source; what is expensive is the filtering and the
  per-source state, and those are what the buses share. Clusters would also need re-clustering
  as sources and camera move, with crossfades.
- **Density-driven beds** (games: crowd loops whose level follows a count per direction): cheap,
  but the sound of the beds is designed, not derived from the scene, and individual cars passing
  between near and far would change character.
- **Stochastic sampling** (Wand and Straßer 2004): render a sampled subset scaled up; efficient for
  static sources, but moving cars would appear and vanish.
- **A cheaper interpolator for the far field**: the optimal-2x read costs about 12 ns per sample, the
  same as in the near tier; with it a far voice equals the full chain without filters to −60 dB,
  which the tests use, and the whole far field still costs about 2 min for 10 000 cars × 60 s.
- **Lower memory for the full chain only** (#32 alone): needed anyway for near voices, but the full
  chain's per-sample cost would still be about 0.2 s per source and minute.

## Consequences

- 10 000 sources over 60 s render in about 3 min and 16 GB on a 16-core node (E18).
- A far voice has no ITD, head shadow or rear low-pass, a per-band instead of a per-source air
  absorption, a single broadband visibility, no playback-rate clamp, and a 8-control-point fade at
  jumps instead of a crossfaded held branch. Which sources are far is decided by level, so these
  differences concern sources that are quieter than the `detail_voices` loudest of their group.
- With `detail_voices: null`, or whenever every source ranks near, the render is the one before
  this decision, sample for sample.
- The far field reads loops from an unpitched shared cycle: at a pitch other than 1 a car's loop
  starts at another point than in the full chain (another, equally valid, random phase).
- The output stays independent of the number of workers: the far field runs a fixed number of tasks
  per group, each with its own bus filter states, summed in order.
