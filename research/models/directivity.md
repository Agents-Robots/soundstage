# Directivity (cones)

Sources that radiate mainly in one direction: a horn, a jet nozzle, a loudspeaker on a stage.

## Model

The bake records each emitter's forward vector (`forward_axis` of the object, default −Z like
Blender's speakers) in world space per sub-frame (`src_fwd`). At emission time, the angle `β`
between the forward vector and the direction from the emitter to the listener gives the gain, as
in OpenAL, with full cone angles `inner` and `outer`:

```
β ≤ inner / 2              → g_cone = 1
β ≥ outer / 2              → g_cone = 10^(cone_outer_gain_db / 20)
otherwise                  → linear in β between the two
```

Defaults (360°, 360°) make a source omnidirectional; the cone stage is then skipped.

## Choices

| Question | Choice | Alternatives and why not |
|---|---|---|
| Law | OpenAL cone (gain only) | Steam Audio's dipole-weighted directivity: smoother but a different parametrization from Blender's speakers and OpenAL, which users and agents know. Frequency-dependent directivity (dull behind a horn): a later option; the cone would then drive a filter as well. |
| Angle | Emitter forward at emission time, listener at reception time | Current orientation: a turning source would change its sound before the turn could be heard. |
| Interpolation of forward vectors | Linear per piece, normalized | Splines: forward vectors at 120 Hz are smooth enough linearly. |

## Verification

- `tests/test_filters.py::test_cone_law`: gains at 0°, 45° (inner/2), 67.5° (midway), 90°
  (outer/2), 150° for a 90°/180°/−12 dB cone.
- `tests/test_filters.py::test_emitter_facing_away_is_quieter`: facing away renders 12.0 ± 0.1 dB
  quieter than facing the camera.
- `tests/test_end_to_end.py`: the bake writes unit forward vectors.

## References

- OpenAL 1.1 Specification and Reference (`openal11`), source cones.
