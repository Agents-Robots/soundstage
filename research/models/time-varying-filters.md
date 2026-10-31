# Time-varying filters

Every filter in the chain changes its parameters while sound passes through it (a source moving
away gets duller continuously). Done naively, parameter updates cause zipper noise or instability.

## Structures

| Filter | Structure | Parameter path |
|---|---|---|
| Air absorption (2 sections) | TPT state-variable filter, output `lp + c·bp + m·hp` | fitted (g, R, c, m) → `g, k = 2R + g, c, m` at control rate, stepped linearly per sample; `h = 1/(1 + g k)` recomputed per sample |
| Rear cue | TPT one-pole low-pass, mixed with the dry signal | fixed `G`; the mix weight interpolated linearly per sample |
| Head shadow | First-order section with fixed pole | `α` → `b0, b1` at control rate; interpolated linearly per sample; `a1` constant |
| Occlusion low-pass (per ear) | TPT one-pole low-pass | fitted cutoff → `G` at control rate; `G` interpolated linearly per sample |

**TPT one-pole** (Zavalishin's topology-preserving transform, zero-delay feedback): per sample

```
v = G (x − s)
y = v + s
s = y + v
```

It is the bilinear-transform low-pass written in the state-variable form of the analog integrator.
Under modulation it keeps the analog filter's behaviour because the state is the integrator's
state, not a past output that was computed with other coefficients.

**TPT state-variable filter** (Zavalishin, ch. 4): two such integrators in a loop, per sample

```
hp = (x − k s₁ − s₂) · h          k = 2R + g, h = 1 / (1 + g k)
bp = g·hp + s₁,  s₁ = bp + g·hp
lp = g·bp + s₂,  s₂ = lp + g·bp
y  = lp + c·bp + m·hp
```

the bilinear transform of `(1 + c s + m s²) / (1 + 2R s + s²)`. Its states are again the
integrators', so it is stable for every positive `g` and `R` and modulates without zipper noise,
as long as `h` is `1/(1 + g k)` of the `g` and `k` in use: the kernel steps `g`, `k`, `c` and `m`
by per-sample increments between two control points and recomputes `h` from them at every sample.
The first version interpolated `h` like the other coefficients (no division per sample); that
stayed within 5·10⁻⁸ of `1/(1 + g k)` for a source moving from 10 m to 2 km in a minute, but a
source passing the listener at 1.4 m with `doppler_factor` 2 moves its corner by 24 % per control
point, and the inconsistent `h` made the section diverge
([E05](../experiments/E05-air-absorption.md), section 7; #42).

## Choices

| Question | Choice | Alternatives and why not |
|---|---|---|
| Update rate | Fixed control rate (1 kHz) with per-sample linear interpolation of the coefficient | Coefficients per processing block: results depend on the block size (here: the chunk size). Per-sample recomputation of `tan`: more cost for no audible gain. |
| What is interpolated | `G` (TPT) and `b0, b1` (shelf) | Interpolating the cutoff and recomputing: same result at much higher cost. Interpolating direct-form biquad coefficients: intermediate sets can be unstable; `G ∈ (0, 1)` and the fixed shelf pole are stable for every intermediate value. |
| One-pole form | TPT | Direct form I/II one-pole: equivalent when static, worse under fast modulation (Zavalishin). |
| Bypass | `G = 1` when the cutoff is at or above 0.49 `f_s` (or infinite) | Leaving a pole near Nyquist: still colours the top octave. |

All per-sample loops are numba kernels (`kernels.svf_cascade_track`, `kernels.svf_cascade`,
`kernels.rear_shelf_track`, `kernels.onepole_cascade`, `kernels.first_order`) with state arrays
updated in place, so chunked processing equals one long run; each has a plain Python reference
implementation in the tests (the state-variable filter against the direct-form bilinear transform).

## Verification

- `tests/test_kernels.py`: cascade and first-order kernels against references; chunked calls equal
  one call; `G = 1` passes the signal unchanged.
- `tests/test_filters.py::test_air_stage_section_is_minus_3db_at_its_corner`;
  `tests/test_kernels.py::test_svf_track_interpolates_between_control_points`.
- `tests/test_filters.py::test_source_passing_through_the_camera_has_no_steps`: level changes by
  less than 0.5 dB between 1 ms blocks while every filter is modulated.

## References

- V. Zavalishin, "Preserving the LTI system topology in s- to z-plane transforms", 2008
  (`zavalishin2008tpt`); *The Art of VA Filter Design* (`zavalishin2020vafilter`), chapters on
  one-pole and state-variable filters.
- Practitioner discussions on coefficient interpolation and zipper noise:
  [KVR](https://www.kvraudio.com/forum/viewtopic.php?p=8608941),
  [JUCE forum](https://forum.juce.com/t/dsp-noise-glitches-when-automating-frequency-via-slow-lfo/63949).
