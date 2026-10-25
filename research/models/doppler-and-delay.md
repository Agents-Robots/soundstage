# Doppler and delay

Propagation delay and Doppler shift come from one mechanism: reading the source's dry signal
through a time-varying delay ([retarded time](retarded-time.md) gives the delay, the
[fractional-delay read](fractional-delay.md) realizes it).

## Model

For `y(t) = x(t − D(t))` the output frequency is `ω (1 − dD/dt)`: the **playback rate**
`r = 1 − dD/dt` is the Doppler factor (Smith). With `D = τ` from the retarded geometry this is
exact for a moving source, a moving camera and both, including acceleration:

| Case | Rate | 34.3 m/s, 1 kHz |
|---|---|---|
| Source approaching / receding | `c / (c ∓ v)` | 1111 / 909 Hz |
| Camera approaching / receding | `(c ± v) / c` | 1100 / 900 Hz |

### Read delay

```
k      = doppler_factor · source.doppler
τ_read = τ₀ + k (τ − τ₀)            default
τ_read =      k (τ − τ₀)            sync_to_picture (one-shots)
τ_L,R  = τ_read ± ITD / 2           hybrid panner (ITD)
```

`τ₀` is the delay at the source's reference time: for a one-shot the reception of its trigger
(solved as `t_r − τ(t_r) = t_trigger`), for a loop its start frame, otherwise the first frame.
`k = 1` is physical, `k = 0` a constant lag without pitch change, `k > 1` exaggerated Doppler.
`sync_to_picture` removes the lag so the onset lands on its frame; Doppler during the sound stays.

A one-shot with several trigger frames needs one `τ₀` per trigger when `sync_to_picture` is set or
`k ≠ 1`; it is then rendered as one voice per trigger. With `k = 1` and no sync, one read serves
all triggers.

### Rate clamp

`r` is clamped to [0.25, 4] (two octaves). Where the clamp applies, `τ_read` is re-integrated from
the clamped rate, **separately in every run between jumps**, so a cut's delay step is never
smeared into a sweep. Inaudible control points (no retarded solution) are clamped for a stable read
but not counted, so a teleport gap does not produce a "near-supersonic" warning.

## Choices

| Question | Choice | Alternatives and why not |
|---|---|---|
| Doppler mechanism | Time-varying delay from geometry | Pitch shift from radial velocity (games, Blender): no propagation delay, only approximate when both move or accelerate, needs a separate resampler. Blender's speakers produced no Doppler at all in rendered audio ([E01](../experiments/E01-blender-speaker-baseline.md)). |
| Strength control | Scale the delay's variation around `τ₀` | Scaling the velocity: breaks the delay's consistency with the picture. |
| Sync | Per-source `sync_to_picture` for one-shots | Global no-delay mode: loses "heard after seen" for everything. |
| Clamp | [0.25, 4], re-integrated per run | Unclamped: near Mach 1 the rate explodes; supersonic motion has no single solution. |

## Verification

[E08](../experiments/E08-known-answers.md) and `tests/test_propagation.py`:

| Quantity | Expected | Measured |
|---|---|---|
| Click at 343 m | 1.000000 s late | 1.000000 s |
| Source at 34.3 m/s | 1111.1 / 909.1 Hz | 1111.1 / 909.1 Hz |
| Camera at 34.3 m/s | 1100.0 / 900.0 Hz | 1100.0 / 900.0 Hz |
| `k = 0` / `k = 2` | 1000 / 1000, 1222.2 / 818.2 Hz | same |
| `sync_to_picture`, two triggers at 343 m | on their frames | on their frames |

Supersonic approach (330 m/s → rate 26): clamped to 4, warning, finite output.

## Limits

- Near Mach 1 the clamp distorts pitch on purpose; the report warns.
- Doppler of the `standard` interpolator above 1.09× folds content above 22 kHz below 24 kHz
  ([fractional delay](fractional-delay.md)); use `quality = "high"` for extreme Doppler.

## References

- J. O. Smith, *Physical Audio Signal Processing*, "Time-Varying Delay Line Reads" and "Doppler
  Simulation" (CCRMA, online).
- J. O. Smith, S. Serafin, J. Abel, D. Berners, "Doppler Simulation and the Leslie", DAFx-02
  (`smith2002doppler`).
- ADR [0006](../../docs/adr/0006-propagation-retarded-time-delay-line.md),
  [0008](../../docs/adr/0008-cinematic-air-physics.md).
