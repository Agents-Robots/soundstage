# 0009. Per-source processing chain with replaceable models

- Status: Accepted
- Date: 2026-10-25
- Ticket: #9

## Context

Phase 2 adds propagation delay, Doppler, ITD, head shadow, air absorption, rear cue, cones and
cut crossfades; Phase 3 and 4 add occlusion, reverb sends, binaural panning and more. Each of these
models will be tuned or replaced on its own (a better interpolator, another pan law, a measured
air-absorption curve), often to compare two variants by ear. Phase 1's render loop computed gain
and pan inline, which does not scale to a dozen interacting models. The engine must also stay
deterministic (NFR-2) while using several cores (NFR-3).

## Decision

**One path, two signal domains.** Per spatial source:

1. A **path** (`geometry.Path`) is computed once for the render range at the control rate
   (1 kHz): retarded delay, propagation distance, camera-space direction of the retarded source,
   emitter angle, segment and piece indices, and the control points where the geometry jumps
   (cuts, teleports). Every model reads its inputs from the path; nothing recomputes geometry.
2. **Emission side** (mono, before the delay read, at the emission rate `f_s × oversample`): the
   dry timeline, then the emission stages (air absorption, rear low-pass; later occlusion). Their
   parameters are taken from the path and placed on emission time `t − τ`. Mono processing here
   halves the filter cost compared with per-ear filtering. The result is appended to a
   **delay line** (`propagation.DelayLine`), a buffer of emission samples that grows and is trimmed
   as reception chunks advance.
3. **Reception side** (per ear, at `f_s`): read delays per ear (Doppler factor, sync to picture,
   ITD, rate clamp), the fractional-delay **interpolator**, the ear stages (head shadow), then
   gains (distance, cone, rear) and pan gains. At jumps a second, held branch is read and
   crossfaded for 10 ms.

**Stages.** An audio-rate stage is an object with its control-rate parameter tracks and its
filter state, and one method `process(x, a, b)` for the samples `[a, b)` of its domain; calling it
chunk by chunk gives the same result as one call (tests check this). Stages are built per source
by the panner and the source renderer from the path, the source parameters and the scene
settings.

**Models by name.** Each family is a registry (a dict from name to function or class):
interpolators (`hermite4`, `optimal2x`, `sinc`), pan laws (`sine`, `power`), panners
(`amplitude`, `hybrid`), distance models, air absorption. A scene setting picks the model by name
(`quality`, `pan_law`, `panner`, `distance_model`), so variants are compared with
`--set key=value` without a re-bake. The schema's choices are tested to match the registries.

**Kernels.** Per-sample loops (interpolators, one-pole cascades, first-order sections) live in
`engine/kernels.py` as `numba.njit(cache=True, nogil=True)` functions, each with a plain
numpy/Python reference implementation that the tests compare against (ADR 0002).

**Parallel and deterministic.** The render runs chunk by chunk (reception time). Within a chunk,
sources render in a thread pool (numba kernels release the GIL); their contributions are summed in
source order, so the output is bit-identical regardless of thread timing. Each source's renderer
keeps its state between chunks and is used by one thread at a time.

## Alternatives considered

- **Whole-shot processing per source** (no chunks): simpler state, but a 5-minute source at the
  2× emission rate needs about 1 GB of temporaries per thread.
- **Per-ear emission-side filtering** (filters after the read): simpler mapping of parameters,
  twice the filter work, and no gain in accuracy for parameters that change over milliseconds.
- **A generic graph of processing nodes** (as in audio frameworks): more flexible than needed;
  the order of physical effects is fixed, and a fixed chain with replaceable models is easier to
  test and to read.
- **Classes for every model**: functions are enough for stateless laws (gain, pan, cutoff); only
  stateful audio-rate stages are objects.

## Consequences

- Adding a model: write the function or stage, register it under a name, add the name to the
  schema's choices and the spec, add a known-answer test. Nothing else changes.
- Improving a model in place (e.g. the air-absorption fit) touches one module and its tests.
- The emission rate depends on the interpolator (2× for `optimal2x`), so samples are resampled
  once to that rate at load time.
- Parameters that depend on reception geometry (rear cue) are applied on the emission side through
  the `t − τ` mapping; where that mapping jumps back at a cut, the first occurrence wins, which
  only matters inside the 10 ms crossfade.

## Notes

Occlusion (Phase 3) runs on the reception side, per ear after the read, not on the emission side
as anticipated above: the baked visibility already describes the path of the sound heard at each
reception time, so placing it on emission time would retard it twice
([processing chain](../../research/models/processing-chain.md#why-two-signal-domains)).
