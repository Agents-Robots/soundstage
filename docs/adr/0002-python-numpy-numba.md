# 0002. Python with numpy/scipy, numba for per-sample kernels

- Status: Accepted
- Date: 2026-10-25
- Ticket: —

## Context

The engine processes up to ~50 sources over shots of several minutes at 48 kHz. Most of the work
vectorizes (gains, pan, convolution), but time-varying recursive filters and fractional-delay
reads with per-sample positions are loops over samples. The rest of the toolchain (Blender
scripts, render tooling) is Python, and the user and agents work in Python.

## Decision

- Python 3.12, numpy and scipy for everything that vectorizes; soundfile for I/O, soxr for
  resampling, pyloudnorm for loudness.
- Per-sample kernels (one-pole and shelf filters with per-block coefficients, cubic and sinc
  fractional-delay reads) as small `numba.njit` functions, each with a plain numpy reference
  implementation used by tests.
- Parallelism over sources with numba `prange` or threads when needed for NFR-3.

## Alternatives considered

- **Pure numpy**: per-sample recursions via `scipy.signal.lfilter` per block work for fixed
  coefficients but get awkward and slow with coefficients changing every 48 samples; delay reads
  vectorize but sinc reads need large temporaries.
- **Rust or C++ core with Python bindings**: fastest, but a build toolchain, slower iteration and
  harder for agents and the user to change; the expected load does not need it.
- **Cython**: compiled build step for the same gain as numba.

## Consequences

- numba is a core dependency (wheels exist for Python 3.12 on Linux); first-call JIT compile time
  of a few seconds per render, reduced with `cache=True`.
- Kernels are kept small and free of Python objects; the reference implementations double as
  documentation.
- If a later requirement (hundreds of sources, binaural with long HRIRs) outgrows this, a compiled
  core can replace individual kernels behind the same function signatures.

## Notes

Filter coefficients are computed at the 1 kHz control rate and interpolated linearly per sample in
the kernels, rather than held per block ([time-varying filters](../../research/models/time-varying-filters.md));
sources run in a thread pool on `nogil` kernels (ADR [0009](0009-processing-chain.md)).
