# E10: render performance (NFR-3)

**Question.** Does the engine render 50 sources over 5 minutes in at most 5 minutes on a current
desktop CPU, also with the Phase 3 processing (occlusion, reverb, stems)?

## Setup

`tools/benchmark.py` builds a synthetic shot: a slowly moving camera, sources on straight passes at
5–60 m/s repeated every 40 s (so every source teleports back), every fifth source a one-shot every
few seconds; baked at 30 fps with 4 sub-frames; default settings (standard quality, hybrid panner,
air absorption); `--occlusion --reverb hangar --stems` adds visibility that varies between 0 and 1
per source and band, the reverb and the group buses. Machine: AMD Ryzen 9 3950X, 16 cores / 32
threads.

## Results

Output of `e10_performance.py` on an unloaded compute node (AMD Ryzen 9 3950X, 32 threads, after
Phase 3):

| sources | length | workers | render | of which setup | of which audio | real time |
|---|---|---|---|---|---|---|
| 10 | 1 min | 1 | 8.4 s | 1.7 s | 6.8 s | 7.1× |
| 10 | 1 min | 10 | 1.4 s | 0.3 s | 1.0 s | 43.0× |
| 50 | 1 min | 1 | 37.7 s | 4.2 s | 33.5 s | 1.6× |
| 50 | 1 min | 32 | 7.8 s | 1.6 s | 6.1 s | 7.7× |
| **50** | **5 min** | **32** | **41.9 s** | 9.5 s | 32.4 s | **7.2×** |
| 50 | 5 min + occlusion, reverb, stems | 32 | 63.1 s | 18.3 s | 44.7 s | 4.8× |

The target (≤ 300 s) is met with a factor of 7, and of 4.8 with the Phase 3 processing on every
source: visibility that never stops changing (so every source runs its occlusion filter and its
cutoff fit at every control point), the hangar reverb (an 11 s impulse response, synthesized in
1.2 s) and stems. Setup includes the per-source geometry and the air-absorption fit (about 1 s,
once per process). Real shots: 115 sources, 120 s in 48 s (Phase 2); 178 sources with occlusion,
reverb and 11 stems in 123 s.

The Phase 2 measurement (before Phase 3, in the development container with 24 threads shared with
other work) gave 46.2 s for 50 sources × 5 minutes.

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
.venv/bin/python research/experiments/scripts/e10_performance.py    # about 3 minutes
.venv/bin/python tools/benchmark.py --sources 50 --minutes 5        # the headline case only
.venv/bin/python tools/benchmark.py --sources 50 --minutes 5 --occlusion --reverb hangar --stems
```
