# 0006. Delay and Doppler from retarded time and a fractional-delay read

- Status: Accepted
- Date: 2026-10-25
- Ticket: —

## Context

Moving sources and a moving camera need Doppler. The user chose physical behaviour (propagation
delay, Doppler from both motions) with a strength control
(ADR [0008](0008-cinematic-air-physics.md)). The engine renders offline, so it can look at the
whole trajectory and the whole dry signal at once.

## Decision

- For each reception time `t`, solve the retarded time: the delay `τ` with
  `τ = |s(t − τ) − p(t)| / c` (fixed-point iteration at a 1 kHz control rate).
- Read the source's dry signal at emission time `t − τ_read(t)` with fractional-delay
  interpolation (cubic Hermite; windowed sinc as high quality). Doppler, delay, and their
  interplay with both motions follow from this single mechanism.
- Strength `k` scales the variation of the delay around its value at the source's start
  (`τ_read = τ₀ + k (τ − τ₀)`); `sync_to_picture` drops `τ₀` for one-shots.
- All direction and distance parameters use the retarded source position, so a sound is heard from
  where it was emitted.
- ITD is a small per-ear offset on the read delay (Woodworth formula), not a second retarded-time
  solve per ear.

Formulas and defaults: [spec/signal-model.md](../spec/signal-model.md#propagation-delay-doppler-itd).

## Alternatives considered

- **Pitch shift from radial velocity** (`f' = f · c / (c − v_r)`, as game engines and Blender do):
  no propagation delay, needs a separate resampler, and the pitch curve is only an approximation
  when source and listener both move or accelerate.
- **Per-ear retarded time**: geometrically exact ITD, but no head-shadow diffraction and twice the
  geometry work; the Woodworth offset matches spherical-head ITD better and can be scaled for
  speaker playback.
- **Segment-wise static rendering** (source jumps between positions, as done with
  pyroomacoustics): audible steps, no true Doppler.

## Consequences

- Doppler is exact for any motion below Mach 1. Near and above Mach 1 the read rate is clamped
  (FR-51) and a warning is reported.
- Distant events are heard late, as in reality; `sync_to_picture` exists for shots where this
  would look like a sync error.
- The dry signal must exist before the shot start (pre-roll) and trajectories must be baked with
  padding of at least the longest delay.
- Camera cuts need special handling (segment-wise geometry, crossfade), since the delay jumps.

## Notes

Later findings that refine the implementation, not the decision (Phase 2):

- The standard read is Niemitalo's 6-point optimal-2× polynomial on a 2× oversampled,
  pre-emphasized signal; cubic Hermite stays as a test reference only
  ([fractional delay](../../research/models/fractional-delay.md), E03, E04).
- The retarded-time solver adds Newton steps after two fixed-point steps; fixed-point iteration
  alone was 1.8 % off in pitch at Mach 0.5 ([retarded time](../../research/models/retarded-time.md), E07).
