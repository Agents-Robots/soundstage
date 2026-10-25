# Coordinates and time

The frames of reference every model uses.

## Space

- **World**: Blender world coordinates, scaled to metres by the scene's `unit_settings.scale_length`
  (the bake multiplies positions by it).
- **Listener**: the camera's world matrix with scale removed: rotation `R`, position `p`. Blender
  camera axes: **+X right, +Y up, −Z forward**.
- **Camera space** of a world point `s`: `q = Rᵀ (s − p)`; `x > 0` right, `y > 0` up, `z < 0` in
  front, `z > 0` behind.
- Derived with `r = |q|` and the softened distance `r_e = sqrt(r² + r_min²)`, `r_min = 0.25 m`:
  lateral sine `λ = x / r_e` (pan, ITD, head shadow) and rear factor `ρ = max(0, z / r_e)`
  (rear cue). The softening keeps both smooth when a source passes through the camera.

## Time

- Frame rate `F = fps / fps_base` (exact for 23.976 = 24/1.001 and 29.97 = 30/1.001).
- Time of frame `f`: `t = (f − frame_start) / F`; sub-frames are fractional `f`.
- Output sample `n` ↔ `t = n / f_s`, `f_s = 48 kHz`; **sample 0 = the first frame**; length
  `round((frame_end − frame_start + 1) · f_s / F)`.
- **Emission time** (when sound leaves a source) and **reception time** (when it is heard) differ by
  the delay `τ`; the dry signal lives in emission time, the output in reception time.
- **Control rate**: geometry and all model parameters on a uniform grid of reception times, every
  48 output samples (1 kHz). Gains and filter coefficients are interpolated linearly per sample,
  delays with a Catmull-Rom curve, never across a jump ([cuts and teleports](cuts-and-teleports.md)).

## Why 1 kHz

Geometry changes slowly compared with audio; 1 kHz resolves the fastest parameter changes that
occur (a source passing the camera at close range changes direction over tens of milliseconds)
while costing about 2 % of the audio work. Delays need a smooth curve between control points
because the playback rate is their derivative: linear interpolation would step the rate every
millisecond.

## References

- [spec/signal-model.md](../../docs/spec/signal-model.md#coordinate-frames),
  [spec/scene-format.md](../../docs/spec/scene-format.md).
