# E20: memory a near voice holds

**Question.** With the far field (E18) a render's memory follows the near voices alive at once,
at 55–110 MB each at the peak. What does a near voice hold, and how much of it is needed (#32)?

## Setup

`e20_render_memory.py`: the E18 scene with 1000 cars (60 s, one engine hum loop per car at a pitch
of 0.85–1.15), the first 30 s at `detail_voices` 128, 16 workers, on the workstation. Every
`SpatialRenderer` built is recorded and the bytes of the numpy arrays it holds summed per
attribute; tracemalloc gives the traced peak and the traced memory at the far field's busiest
call, the process its peak RSS. Before: 7e92f98; after: the dry signal keeps only what it reads.

## Results

| | held per near renderer (MB) | of it: dry signal | air stage | traced peak (GB) | traced at the busiest chunk (GB) | peak RSS (GB) |
|---|---|---|---|---|---|---|
| before (7e92f98) | 11.9 | 9.2 | 1.1 | 12.3 | 9.5 | 14.8 |
| after | 4.6 | 2.4 | 0.6 | 7.7 | 4.4 | 7.4 |

692 near renderers were built, at most 253 alive at once.

- A loop renderer kept the resampled sample (one per car, since every car has its own pitch), its
  loop cycle and the prefiltered cycle, all in float64; the dry timeline reads only the last. The
  plain cycle served only the culling estimate's block energies, which are now computed once when
  the renderer is built. The remaining cycle is stored in float32 (rounding about 150 dB down).
- The air stage kept its section parameters beside the coefficients derived from them; it keeps
  the coefficients only (the culling estimate recovers the parameters from them).
- The render's peak halves. What a near voice still costs beyond its own arrays are the per-chunk
  buffers of the voices rendered at once.

## Reproduce

Needs E18's scene (`e18_traffic.py run bake`).

```bash
.venv/bin/python research/experiments/scripts/e20_render_memory.py --checkout <a checkout of 7e92f98>
.venv/bin/python research/experiments/scripts/e20_render_memory.py
```
