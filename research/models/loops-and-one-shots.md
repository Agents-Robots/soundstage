# Loops and one-shots

The dry signal of a source: what it emits, in emission time, before any propagation.

## Model

- **One-shot**: the sample starts at the emission time of its trigger frame (a list of frames
  gives several triggers), with an optional raised-cosine fade-in.
- **Loop**: one *cycle* is built from the sample with its tail crossfaded into its head, then
  tiled from the loop start (its frame, or before the shot) to its end frame plus fade-out. The
  start phase is `loop_phase` seconds into the cycle, or random, seeded from the source id
  (renders are bit-identical, NFR-2).
- **Seam crossfade** (`loop_crossfade`, 50 ms): gains `a` (fade-in) and `b` (fade-out) satisfy
  `a² + b² + 2ρab = 1`, where `ρ` is the correlation of the overlapping head and tail. The power of
  `a·x₁ + b·x₂` is `(a² + b² + 2ρab)·P`, so the level stays constant: equal power for uncorrelated
  material (`ρ = 0`), equal gain for identical material (`ρ = 1`).
- Spatial sources are built at the emission rate (2× output for the standard interpolator) and the
  interpolator's pre-emphasis is applied once: to the one-shot sample (which then starts 31 samples
  early, the FIR's half length) or circularly to the loop cycle (exactly periodic).
- **Voices**: a one-shot with several triggers is rendered as one voice per trigger when each needs
  its own reference delay (`sync_to_picture`, or a Doppler factor ≠ 1); see
  [Doppler and delay](doppler-and-delay.md). Each voice covers the whole shot, but
  [culling](culling.md) skips the chunks in which it is silent.

## Choices

| Question | Choice | Alternatives and why not |
|---|---|---|
| Seam law | Correlation-adaptive (Fink, Holters, Zölzer) | Equal power: +2.9 dB bump at the seam of correlated material (tonal loops, engine hums). Linear: −2.9 dB dip on uncorrelated material (noise, ambience). [E02](../experiments/E02-loop-crossfade.md). |
| Correlation | One `ρ` per loop from the whole overlap, clipped to [0, 1] | Time-varying correlation: more accurate for loops whose head and tail drift apart, rarely needed. Negative correlation is clipped: it would demand gains above 1. |
| Random phase | Seeded from the source id | Unseeded: renders not reproducible. Phase 0 for all: many copies of the same loop start in step and comb. |
| Pre-emphasis | Once per source on sample or cycle | Per chunk on the dry timeline: same result, the largest cost of a render ([E10](../experiments/E10-performance.md)). The small difference at fade edges (fade applied after instead of before the 0.3 ms FIR) is far below audibility. |

## Verification

- [E02](../experiments/E02-loop-crossfade.md): seam level, min/max of 400-sample windows: tone
  −0.07/+0.04 dB, noise −0.74/+0.54 dB (the noise's own window variance), constant 0.00 dB.
- `tests/test_signals.py`: seam without steps; level within 1 dB across the seam for tone, noise and
  constant; exact repetition without crossfade; seeded phase; fades; one-shot placement.

## References

- M. Fink, M. Holters, U. Zölzer, "Signal-Matched Power-Complementary Cross-Fading and Dry-Wet
  Mixing", DAFx-16 (`fink2016`).
