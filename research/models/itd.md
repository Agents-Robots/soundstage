# Interaural time difference (ITD)

A source on the right reaches the right ear first. In the `hybrid` panner the left and right
channels get slightly different read delays.

## Model

Woodworth's spherical-head formula on the lateral angle `θ = asin(λ)` of the retarded direction:

```
ITD = itd_scale · (a / c) · (θ + sin θ)          a = head_radius = 0.0875 m
τ_L = τ_read + ITD / 2,   τ_R = τ_read − ITD / 2
```

At 90° with `itd_scale = 1`: 0.656 ms (31.5 samples at 48 kHz). The default `itd_scale = 0.5`
gives 0.328 ms. The offset is applied in the read delay, so it is sample-accurate and changes
smoothly; there is no second retarded-time solve per ear.

## Background and choices

| Question | Choice | Alternatives and why not |
|---|---|---|
| Formula | Woodworth `(a/c)(θ + sin θ)` | Per-ear retarded time (ears as points 17.5 cm apart): `(2a/c) sin θ`, 0.51 ms at 90°, ignores the path around the head. Woodworth's ray-traced path around a sphere holds above about 2 kHz; at low frequencies diffraction makes the ITD larger (Kuhn 1977: about `3 (a/c) sin θ`, 0.77 ms at 90°). ITD is used here as a cue on loudspeakers, not as a binaural reproduction, so the high-frequency formula is enough. |
| Strength | `itd_scale = 0.5` *(tune)* | Full ITD: on loudspeakers both ears hear both channels, so inter-channel delay acts as time panning; Lee and Rumsey found time panning unreliable for continuous sources with a high fundamental, while level panning works for all sources. Delayed correlated channels also comb-filter in a mono downmix. Half strength adds width without dominating. `0` for mono-critical deliveries. |
| Ear positions | ±90° (the lateral axis) | Brown and Duda place the ear canals at ±100°, slightly behind; see [head shadow](head-shadow.md). |

## Verification

- [E08](../experiments/E08-known-answers.md): measured inter-channel lag (cross-correlation of 4×
  upsampled channels, noise source at 90°): 0.656 ms at `itd_scale` 1, 0.328 ms at 0.5.
- `tests/test_propagation.py::test_itd_at_90_degrees`: within one sample at 4× oversampling.

## References

- R. S. Woodworth, *Experimental Psychology*, 1938 (formula as used by Brown and Duda, `brown1998`).
- G. F. Kuhn, "Model for the interaural time differences in the azimuthal plane", J. Acoust. Soc.
  Am. 62(1), 1977 (no open copy).
- H. Lee, F. Rumsey, "Level and Time Panning of Phantom Images for Musical Sources", JAES 2013
  ([abstract](https://eprints.hud.ac.uk/19670)).
- ADR [0007](../../docs/adr/0007-stereo-ear-model.md).
