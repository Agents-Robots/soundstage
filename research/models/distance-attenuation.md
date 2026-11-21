# Distance attenuation

Loudness as a function of how far the sound travelled.

## Model

The distance is the **propagation distance** `d = c τ` from the [retarded time](retarded-time.md),
not the source's current distance: a passing ship is as loud as it was where the sound left it.
Clamped to the reference and maximum distance `d' = clamp(d, ref, max)` (no upper clamp when
`max_distance` is null), the gain follows one of the OpenAL distance models:

| Model | Gain | Behaviour |
|---|---|---|
| `inverse_clamped` (default) | `ref / (ref + rolloff (d' − ref))` | rolloff 1: −6.02 dB per doubling, the free-field point source |
| `linear_clamped` | `max(0, 1 − rolloff (d' − ref) / (max − ref))` | reaches 0 at `max_distance` |
| `exponential_clamped` | `(d' / ref)^(−rolloff)` | rolloff 1 equals inverse beyond `ref` |
| `none` | 1 | beds or stylized sounds |

`ref_distance` is the distance of full level (1 m by default; for a large source, about its
size); the gain never exceeds 1 inside it, which also keeps a source passing through the camera
finite.

## Choices

| Question | Choice | Alternatives and why not |
|---|---|---|
| Laws | OpenAL's clamped models | They are what Blender's speakers, OpenAL and most game engines use, so tags translate directly; Blender has the same set (one model per scene there, one per source here). |
| Distance | Propagation distance | Current distance: the level would lead the sound by the travel time (a far explosion would get louder before it is heard). |
| Near field | Clamp at `ref_distance` | 1/r without clamp: infinite gain at the camera. |

## Verification

- `tests/test_gain_pan.py`: −6.02 dB per doubling; linear and exponential laws; `max_distance`.
- `tests/test_render.py`: rendered level drops 6.02 ± 0.1 dB at twice `ref_distance`.
- [E01](../experiments/E01-blender-speaker-baseline.md): over the flyby, SoundStage follows the
  inverse law within ±0.02 dB of the retarded distance; Blender's speakers within ±0.48 dB of the
  current distance.

## References

- OpenAL 1.1 Specification and Reference (`openal11`), distance models.
