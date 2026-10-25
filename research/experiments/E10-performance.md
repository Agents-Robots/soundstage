# E10: render performance (NFR-3)

**Question.** Does the Phase 2 engine render 50 sources over 5 minutes in at most 5 minutes on a
current desktop CPU?

## Setup

`tools/benchmark.py` builds a synthetic shot: a slowly moving camera, sources on straight passes at
5–60 m/s repeated every 40 s (so every source teleports back), every fifth source a one-shot every
few seconds; baked at 30 fps with 4 sub-frames; default settings (standard quality, hybrid panner,
air absorption). Machine: AMD Ryzen 9 3950X, 16 cores / 24 threads available to the container,
46 GB RAM.

## Results

Output of `e10_performance.py`:

| Sources | Length | Workers | Render | of which setup | of which audio | Real time |
|---|---|---|---|---|---|---|
| 10 | 1 min | 1 | 6.4 s | 1.9 s | 4.5 s | 9.3× |
| 10 | 1 min | 10 | 1.5 s | 0.4 s | 1.1 s | 39.5× |
| 50 | 1 min | 1 | 27.6 s | 4.9 s | 22.7 s | 2.2× |
| 50 | 1 min | 24 | 8.4 s | 1.8 s | 6.6 s | 7.1× |
| **50** | **5 min** | **24** | **46.2 s** | 10.6 s | 35.5 s | **6.5×** |

The target (≤ 300 s) is met with a factor of 6.5. Setup includes the per-source geometry and the
air-absorption fit (about 1 s, once per process). A real shot from a user project (115 sources,
120 s) rendered in 48 s.

## How it got there

| Step | 50 sources × 5 min |
|---|---|
| First working Phase 2 engine | 253.8 s; 24 threads barely faster than one: per-sample helpers in numpy (`np.interp`, control-rate interpolation, the pre-emphasis `np.convolve`) held the GIL |
| Control-rate interpolation, emission parameter interpolation and FIR moved into numba kernels (`nogil`) | threads scale (3.3× on 10 workers in the small case) |
| Pre-emphasis applied once per source to the sample or loop cycle instead of per chunk; fused interpolate-and-filter kernels; per-frame statistics vectorized and computed in the workers; renderers built in parallel | **47.9 s**, then 46.2 s |

The per-source profile after these steps is spread over the one-pole cascade at 96 kHz, the
6-point reads, control-rate interpolation and the dry timeline, with no single dominant cost.

## Reproduce

```bash
.venv/bin/python research/experiments/scripts/e10_performance.py    # about 2 minutes
.venv/bin/python tools/benchmark.py --sources 50 --minutes 5        # the headline case only
```
