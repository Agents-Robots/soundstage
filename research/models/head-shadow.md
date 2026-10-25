# Head shadow

The head blocks high frequencies on the far side and slightly boosts them on the near side. In the
`hybrid` panner each channel gets a first-order shelf.

## Model

Brown and Duda's spherical-head shadow filter, per ear, with `θ` the angle between that ear's axis
and the source direction (`cos θ_R = λ`, `cos θ_L = −λ`, `λ` the lateral sine):

```
H(s) = (1 + α(θ) s / (2ω₀)) / (1 + s / (2ω₀)),        ω₀ = c / a
α(θ) = (1 + α_min/2) + (1 − α_min/2) cos(θ · 180° / θ_min),   α_min = 0.1, θ_min = 150°
α_eff = 1 + head_shadow · (α(θ) − 1)
```

DC gain 1, high-frequency gain `α`: +6 dB at the ear's axis (θ = 0), −2.4 dB in front (90°),
−20 dB at 150°, rising again to −11 dB straight opposite (180°, the "bright spot" behind a sphere).
The corner `2ω₀ = 2c/a` is 1.25 kHz for `a` = 8.75 cm.

**Discretization.** Bilinear transform prewarped at the pole `2ω₀`:

```
k  = 1 / tan(2ω₀ / (2 f_s))
b0 = (1 + α k) / (1 + k),   b1 = (1 − α k) / (1 + k),   a1 = (1 − k) / (1 + k)
y[n] = b0 x[n] + b1 x[n−1] − a1 y[n−1]
```

The pole does not depend on `α`, so a moving source only changes the numerator: `b0` and `b1` are
interpolated linearly per sample between control points. Every intermediate filter is a valid
first-order shelf with the same stable pole, so modulation cannot cause instability or zipper noise
([time-varying filters](time-varying-filters.md)).

| θ from the ear axis | α (full) | at 10 kHz, full | α (default 0.5) | at 10 kHz, 0.5 |
|---|---|---|---|---|
| 0° | 2.000 | +6.0 dB | 1.500 | +3.5 dB |
| 45° | 1.608 | +4.1 dB | 1.304 | +2.3 dB |
| 90° | 0.756 | −2.4 dB | 0.878 | −1.1 dB |
| 135° | 0.146 | −14.9 dB | 0.573 | −4.7 dB |
| 150° | 0.100 | −16.7 dB | 0.550 | −5.1 dB |
| 180° | 0.281 | −10.5 dB | 0.641 | −3.8 dB |

(The discrete filter at 10 kHz is a little short of the analog high-frequency limit `20 log α`
because the shelf is still rising there.) Curves: [E06](../experiments/E06-ear-model.md).

## Choices

| Question | Choice | Alternatives and why not |
|---|---|---|
| Model | Brown–Duda one-pole/one-zero shelf | Measured HRTFs (binaural): colour the sound on loudspeakers; planned as the `binaural` panner (Phase 4). Rayleigh's exact sphere solution: an infinite series, no benefit for a cue. |
| Strength | `head_shadow = 0.5` *(tune)* | Full strength: on loudspeakers the listener's real head adds its own shadow; full strength would double it. |
| Ear axis | ±90° (lateral sine) | Brown and Duda put the ear canals at ±100° azimuth (slightly behind). With ±100°, a source in front is darker than one behind; the lateral sine is symmetric front/back, and the rear is marked by the separate [rear cue](rear-cue.md) instead. |
| Discretization | Bilinear, prewarped at the pole | Impulse invariance: aliasing of the shelf; matched-z: less accurate high-frequency gain. |

The formula for `α(θ)` is checked against secondary sources; Brown and Duda's equations could not be
rendered here (no PDF renderer installed), while the surrounding text (the filter as their
equation 3, ear positions at ±100°) was read from the paper.

## Verification

- `tests/test_filters.py::test_head_shadow_matches_brown_duda`: α at 0°, 150°, 180°; discrete
  response within 0.5 dB of the analog one up to 4 kHz; strength 0 is flat.
- `tests/test_filters.py::test_shelf_stage_chunks_equal_one_call`.

## References

- C. P. Brown, R. O. Duda, "A Structural Model for Binaural Sound Synthesis", IEEE TSAP 1998
  (`brown1998`).
- Apple's Sound Sprocket used the same filter ([auditory.org posting](https://auditory.org/postings/1996/175.html)).
