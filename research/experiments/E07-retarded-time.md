# E07: retarded-time solver accuracy

**Question.** The spec proposed four fixed-point iterations for `τ = |s(t − τ) − p| / c`, with
an error contracting by `v/c` per step. How large is the error for fast sources, and what does it
do to the pitch?

## Setup

A source moves at constant velocity `v` (Mach 0.1 to 0.95) along a line 20 m in front of a static
camera, passing it at t = 25 s; reception times 24–27 s are evaluated. The pass is late in a long
bake so that every emission time lies inside the baked range (a source approaching at Mach 0.95 is
heard 1 s before its pass with sound emitted about 20 s earlier). The analytic delay solves the
quadratic `|s₀ + v(t − τ)| = cτ`. Pitch error: deviation of `1 − dτ/dt` from the exact rate.

## Results

Output of `e07_retarded_time.py` (largest error over the window):

| Mach | Fixed point ×4: τ error | pitch error | Engine (2 fixed point + Newton): τ error | pitch error |
|---|---|---|---|---|
| 0.1 | 1.5e-6 s | 0.000 % | 7.0e-11 s | 0.000 % |
| 0.3 | 1.1e-3 s | 0.085 % | 3.0e-14 s | 0.000 % |
| 0.5 | 3.1e-2 s | **1.8 %** | 5.0e-10 s | 0.000 % |
| 0.8 | 1.3 s | **30 %** | 2.1e-10 s | 0.000 % |
| 0.95 | 15 s | **78 %** | 1.5e-9 s | 0.000 % |

A first run placed the pass at t = 2 s; both solvers then showed large errors because the emission
times fell before the baked range, where positions are held. That is the situation the bake's
padding warning exists for.

## Conclusion

Fixed-point iteration is fine for slow sources but wrong for fast ones (1.8 % pitch error, about a
third of a semitone, at Mach 0.5). Newton's method with the spline velocity converges to about
1e-9 s for any subsonic speed ([retarded time](../models/retarded-time.md)).

## Reproduce

```bash
.venv/bin/python research/experiments/scripts/e07_retarded_time.py
```
