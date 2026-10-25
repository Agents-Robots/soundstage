# E08: Phase 2 known answers

**Question.** Does the rendered output meet the physical known answers of the Phase 2 acceptance
criteria (issue #8)?

## Setup

Synthetic scenes rendered through the full engine (`render.render`), the same scenes as the unit
tests: a click at 343 m; a 1 kHz sine passing at 34.3 m/s 3 m from the camera (source moving, or
camera moving), with the frequency measured from zero crossings over 0.5 s windows far from the
pass; a noise burst at 90° for the ITD (cross-correlation of the 4× upsampled channels); a camera
cut from 5 m to 100 m from a sine source. Plain settings (amplitude panner, no air absorption)
unless the quantity needs the hybrid panner.

## Results

Output of `e08_known_answers.py`:

| Quantity | Expected | Measured |
|---|---|---|
| delay of a click at 343 m | 1.000000 s | 1.000000 s |
| Doppler, moving source, k = 1 | 1111.1 / 909.1 Hz | 1111.1 / 909.1 Hz |
| Doppler, moving camera, k = 1 | 1100.0 / 900.0 Hz | 1100.0 / 900.0 Hz |
| Doppler, moving source, k = 0 | 1000.0 / 1000.0 Hz | 1000.0 / 1000.0 Hz |
| Doppler, moving source, k = 2 | 1222.2 / 818.2 Hz | 1222.2 / 818.2 Hz |
| ITD at 90°, itd_scale 1.0 | 0.656 ms | 0.656 ms |
| ITD at 90°, itd_scale 0.5 | 0.328 ms | 0.328 ms |
| camera cut 5 m → 100 m: level change | −26.02 dB | −26.02 dB |
| camera cut: frequency 12–60 ms after | 1000.0 Hz | 1000.0 Hz |
| camera cut: largest sample step / the sine's own | ≤ 1.5 | 1.00 |

## Conclusion

All Phase 2 physical criteria are met to the displayed precision. The remaining criteria are the
performance target ([E10](E10-performance.md)) and the listening judgement (#15), both met.

## Reproduce

```bash
.venv/bin/python research/experiments/scripts/e08_known_answers.py
```
