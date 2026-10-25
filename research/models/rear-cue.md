# Rear cue

Two loudspeakers cannot place a sound behind the listener. Real ears get a front/back cue from
the pinna (sounds from behind are duller). The rear cue imitates that mildly so a source passing
behind the camera is marked; the picture carries the rest.

## Model

With the rear factor `ρ = max(0, z / r_e)` of the retarded direction in camera space (0 in front
and at the side, → 1 straight behind):

```
y = x + ρ (LP(x) − x)            LP: TPT one-pole low-pass at rear_cutoff_hz (6 kHz)
g_rear = 10^(rear_gain_db · ρ / 20)                       (rear_gain_db = −2)
```

The low-pass mixed with the dry signal by `ρ` is a first-order high-frequency shelf whose depth
grows with `ρ`. It is applied on the emission side (mono), the gain with the other gains. Only the
`hybrid` panner uses it.

| ρ | 1 kHz | 6 kHz | 12 kHz | 18 kHz |
|---|---|---|---|---|
| 0 | 0.00 | 0.00 | 0.00 | 0.00 dB |
| 0.5 | −0.08 | −2.04 | −4.44 | −5.66 dB |
| 1 | −0.11 | −3.01 | −8.34 | −15.44 dB |

(before `g_rear`; [E06](../experiments/E06-ear-model.md))

## Choices

| Question | Choice | Alternatives and why not |
|---|---|---|
| Filter | Dry/low-pass mix by `ρ` | A low-pass whose cutoff moves from 20 kHz at the side to 6 kHz behind (the original spec): a one-pole at 20 kHz still takes about 1–2 dB off 15 kHz for **every** source in front, and adds phase delay (found when a click's peak moved by a sample). The mix is exactly transparent at `ρ = 0` and bypassed when a source is never behind. |
| Strength | 6 kHz, −2 dB (kept after listening, #15) | Stronger cues make sources behind sound muffled rather than "behind". |
| Input | `ρ` from the camera-space z of the retarded direction | Azimuth beyond ±90°: discontinuous where the source crosses the lateral axis. |

## Verification

`tests/test_filters.py::test_rear_cue_low_passes_and_attenuates_a_source_behind`: a noise source
straight behind against the same source in front: −2.0 ± 0.2 dB at 200 Hz, −5.0 ± 0.6 dB at 6 kHz
(the gain plus the low-pass's −3 dB at its cutoff).

## References

- ADR [0007](../../docs/adr/0007-stereo-ear-model.md) (rear cue as part of the hybrid panner).
