# Spec: signal model

How the engine turns a scene file into audio: frames of reference, time base, the processing
chain per source, the formulas and their defaults. Starting values marked *(tune)* are first
guesses to be adjusted by ear in the phase that introduces them; record the tuned value and the
reason here.

Decisions behind this model: ADR [0006](../adr/0006-propagation-retarded-time-delay-line.md)
(propagation), [0007](../adr/0007-stereo-ear-model.md) (ears and panning),
[0008](../adr/0008-cinematic-air-physics.md) (physics defaults).

## Coordinate frames

- **World**: Blender world coordinates, scaled to metres by `units.scale_length`.
- **Listener**: the camera's world matrix `M(t)` with scale removed: rotation `R(t)`, position
  `p(t)`. Blender camera axes: **+X right, +Y up, −Z forward** (view direction).
- **Camera-space source vector** of a world point `s`: `q = Rᵀ (s − p)`, components
  `(x, y, z)`: `x > 0` right, `y > 0` up, `z < 0` in front, `z > 0` behind.
- Derived quantities, with `r = |q|` and a near-field softened distance `r_e = sqrt(r² + r_min²)`,
  `r_min = 0.25 m` (keeps pan and filters smooth when a source passes through the camera):
  - lateral sine `λ = x / r_e` ∈ (−1, 1), lateral angle `θ_l = asin(λ)`
  - rear factor `ρ = max(0, z / r_e)` ∈ [0, 1) (0 at the side or in front, → 1 straight behind)

## Time base and alignment

- Frame rate `F = fps / fps_base` (exact for 23.976 = 24/1.001, 29.97 = 30/1.001).
- Time of frame `f` relative to the shot: `t(f) = (f − frame_start) / F`. Sub-frames are
  fractional `f`.
- Output sample `n` ↔ `t = n / fs`, `fs = 48000` Hz. **Sample 0 = first frame.**
- Output length: `round((frame_end − frame_start + 1) · fs / F)` samples, so the audio ends with
  the last frame's duration.
- Internally the engine simulates from `t_min = t(frame_start − pad_frames_before)` (pre-roll) so
  sound emitted before the first frame arrives correctly, and trims to `[0, length)` at the end.

## Processing chain (per source)

```
sample ─▶ decode, downmix, resample to fs, pitch ─▶ dry timeline x(t_e)   (loops tiled, one-shots placed, fades)
                                                            │
geometry (control rate 1 kHz):                              │
  listener p,R(t) and source s(t) splines                   ▼
  ─▶ retarded time τ_c(t) ─▶ τ_read,L/R(t) (Doppler factor, sync, ITD) ─▶ fractional-delay read ─▶ y_L, y_R
  ─▶ q_ret = Rᵀ(s(t−τ_c) − p)  ─▶ distance gain, cone, pan gains, rear cue, occlusion, filter cutoffs
                                                                                  │
y_L, y_R ─▶ air-absorption LP ─▶ directional LP (rear/occlusion) ─▶ head shadow (per ear) ─▶ gains ─▶ group bus
                                                     └─▶ reverb send (mono, pre-pan) ─▶ scene reverb ─▶ master
```

All spatial parameters use the **retarded** source position `s(t − τ_c)`: the sound is heard from
where it was emitted, with the loudness of the distance it actually travelled.

Bed sources (`spatial: false`) skip everything between the dry timeline and the group bus except
gain and fades.

## Dry timeline

- Decode with libsndfile (WAV, FLAC, OGG), convert to float64. Spatial sources: stereo samples are
  downmixed `(L + R) / 2`. Beds keep stereo; mono beds go to both channels at −3.01 dB.
- Resample to `fs` with soxr (VHQ). Apply `pitch` as a further soxr ratio `1 / pitch`.
- **One-shot**: the sample starts at emission time `t_trig = t(frame)`; zero elsewhere. `fade_in`
  as a raised-cosine ramp if set.
- **Loop**: tiled from the loop start (`t(frame)`, or `t_min` if `frame` is null) to the loop end
  (`t(end_frame) + fade_out`, or the end of the simulated range). The seam uses an equal-power
  crossfade of `loop_crossfade` seconds (the tail overlaps the head). Start offset `loop_phase`
  seconds into the sample; `"random"` = uniform in [0, sample length), seeded from the source id.
  Fades are raised-cosine.
- The dry timeline covers emission times from `t_min − max delay` to the end, so every read
  position exists.

## Trajectories and control rate

- Baked positions (`substeps` per frame) are interpolated with cubic splines (scipy
  `CubicSpline`, not-a-knot) in time, **separately per segment** between cuts. The listener
  rotation is interpolated by spherical linear interpolation of quaternions between time samples.
- Geometry is evaluated at the **control rate** `f_ctl = 1000 Hz` (48-sample blocks). Delays are
  upsampled from control rate to audio rate with cubic interpolation (they are smooth); gains are
  interpolated linearly per sample; filter coefficients are updated per block.

## Propagation: delay, Doppler, ITD

**Retarded time.** For reception time `t` and listener position `p(t)`, the propagation delay
`τ_c(t)` solves `τ = |s(t − τ) − p(t)| / c`. Fixed-point iteration at control rate:

```
τ⁽⁰⁾ = |s(t) − p(t)| / c
τ⁽ᵏ⁺¹⁾ = |s(t − τ⁽ᵏ⁾) − p(t)| / c        (4 iterations)
```

The iteration contracts with factor `|v_s| / c`, so 4 iterations leave a relative error of
`(v_s/c)⁴` (1e-4 at Mach 0.1). Listener motion needs no iteration (`p` is taken at reception
time).

**Doppler factor and picture sync.** With `k = doppler_factor · source.doppler` and `τ₀ = τ_c` at
the source's reference time (one-shot: reception of the trigger; loop: its start, or `t_min`):

```
τ_read(t) = τ₀ + k · (τ_c(t) − τ₀)         default
τ_read(t) =      k · (τ_c(t) − τ₀)         sync_to_picture (one-shots only)
```

`k = 1` is physical; `k = 0` freezes the delay (no Doppler, constant lag); `k > 1` exaggerates
Doppler. With `sync_to_picture` the onset lands exactly on `frame`, and the delay variation during
playback (Doppler) remains.

**ITD** (hybrid and binaural panners). Woodworth spherical-head formula on the lateral angle of
the retarded direction:

```
ITD = itd_scale · (a / c) · (θ_l + sin θ_l)        a = head_radius
τ_read,L = τ_read + ITD / 2,   τ_read,R = τ_read − ITD / 2
```

At `θ_l = 90°`, `a = 0.0875 m`, `itd_scale = 1`: ITD = 0.656 ms.

**Playback rate.** `rate(t) = 1 − dτ_read/dt` (> 1 approaching, < 1 receding). It is clamped to
`[0.25, 4.0]` (two octaves); where clamping applies, `τ_read` is re-integrated from the clamped
rate and the report warns (near- or super-sonic motion, FR-51).

**Fractional-delay read.** `y_e(t) = x(t − τ_read,e(t))`, read at fractional sample positions:

- `quality = "standard"`: 4-point cubic Hermite (Catmull-Rom) interpolation.
- `quality = "high"`: Kaiser-windowed sinc, 32 taps, cutoff `0.45 · fs · min(1, 1/rate)`, which
  also band-limits when reading faster than real time.

## Distance gain

`d = c · τ_c` (propagation distance), clamped `d' = clamp(d, ref, max)` (no upper clamp if `max`
is null). As in OpenAL and Blender:

| Model | Gain |
|---|---|
| `inverse_clamped` (default) | `g = ref / (ref + rolloff · (d' − ref))` |
| `linear_clamped` | `g = max(0, 1 − rolloff · (d' − ref) / (max − ref))` |
| `exponential_clamped` | `g = (d' / ref) ^ (−rolloff)` |
| `none` | `g = 1` |

Inverse with rolloff 1: −6.02 dB per doubling of distance (free-field point source).

## Directivity cone

Angle `β` between the emitter's forward vector (at emission time) and the direction from emitter to
listener. With full angles `inner`, `outer` (degrees) and `g_out = 10^(cone_outer_gain_db / 20)`:

```
β ≤ inner/2            → g_cone = 1
β ≥ outer/2            → g_cone = g_out
otherwise              → linear interpolation of g in between
```

## Air absorption

Absorption coefficient approximated as `α(f) = A · α₈ · (f / 8000)²` dB/m, with
`α₈ = 0.1 dB/m` (ISO 9613-1, 20 °C, 50 % RH, *(tune)*) and `A = air_absorption · source.air_absorption`.
Realized as a one-pole low-pass whose cutoff is where the loss reaches 3 dB:

```
f_air(d) = clamp(8000 · sqrt(3 / (A · α₈ · d)), 300, 20000) Hz
```

Examples (`A = 1`): 10 m → 13.9 kHz, 100 m → 4.4 kHz, 1 km → 1.4 kHz.

## Panning

**`amplitude`**: constant-power pan from the lateral sine only:

```
φ = (λ + 1) · π / 4,   g_L = cos φ,   g_R = sin φ          (g_L² + g_R² = 1; centre = −3.01 dB each)
```

**`hybrid`** (default): the amplitude pan above, plus ITD scaled by `itd_scale` (default 0.5,
*(tune)*: full ITD across speakers causes comb filtering in mono downmixes), plus a head-shadow
filter per ear scaled by `head_shadow` (default 0.5, *(tune)*).

Head shadow (Brown & Duda 1998 spherical-head model), per ear, with `θ_e` the angle between that
ear's axis (+X for right, −X for left) and the source direction (`cos θ_R = λ`, `cos θ_L = −λ`):

```
α(θ) = (1 + α_min/2) + (1 − α_min/2) · cos(θ · 180° / θ_min),   α_min = 0.1, θ_min = 150°
α_eff = 1 + head_shadow · (α(θ) − 1)
H(ω) = (1 + j · α_eff · ω / (2ω₀)) / (1 + j · ω / (2ω₀)),   ω₀ = c / a
```

a first-order shelf (up to +6 dB treble at the near ear, down to −20 dB at the far ear at full
strength), discretized with the bilinear transform per control block.

**`binaural`** (Phase 4): replaces pan, ITD and head shadow with HRIR convolution from a SOFA set,
interpolated between measured directions.

## Rear cue

Stereo cannot place a source behind the camera, so behind is marked spectrally:

```
f_rear = 20000 · (rear_cutoff_hz / 20000) ^ ρ          (log interpolation, 20 kHz at the side)
g_rear = 10 ^ (rear_gain_db · ρ / 20)
```

## Occlusion

Visibility `v ∈ [0, 1]` from the bake (fraction of unobstructed rays from the camera to points
within `occlusion_radius` of the emitter) is smoothed with a one-pole follower (60 ms when
becoming occluded, 150 ms when becoming visible, *(tune)*), then:

```
g_occ = 10 ^ ((1 − v) · occlusion_gain_db / 20)                     occlusion_gain_db = −12 (tune)
f_occ = 20000 · (occlusion_cutoff_hz / 20000) ^ (1 − v)             occlusion_cutoff_hz = 1500 (tune)
```

The directional low-pass uses `min(f_rear, f_occ)`; air absorption is a separate stage. Both are
one-pole low-passes with per-block coefficients.

## Reverb send

Each spatial source feeds a mono send, taken after the delay read (centre ear) and before panning:

```
send = 10^(reverb_send_db / 20) · g_dist(d; rolloff/2) · g_occ^0.5 · y_c
```

The send uses half the rolloff, so the reverb falls more slowly with distance than the direct sound
and the direct-to-reverb ratio acts as a distance cue. The sum of sends is convolved (FFT,
partitioned per chunk) with a stereo impulse response: a user file, or a preset synthesized by
seed (decorrelated exponentially decaying noise with RT60, pre-delay and HF damping), so presets
need no licensed files. Presets: `none`, `small_room`, `hall`, `hangar`, `outdoor` *(tune)*.

## Cuts

- **Listener cuts** split reception time into segments. Each segment uses its own listener
  trajectory (splines never cross a cut). The output around a cut is an equal-power crossfade of
  10 ms between the read of the old segment (listener held) and the new one. There is no Doppler
  sweep across the cut.
- **Source teleports** (`src_cuts`): the source trajectory is piecewise; `s(t_e)` is evaluated in
  the piece that contains the emission time, so sound emitted before the jump still comes from the
  old place. The delay discontinuity is handled with the same 10 ms crossfade.

## Mixing and output

- Each source contributes `(g · y_L, g · y_R)` to its group bus, with
  `g = gain · g_dist · g_cone · g_rear · g_occ` and pan gains applied per channel.
- Master = Σ groups + reverb return, times `master_gain_db`.
- Output: WAV via libsndfile, `FLOAT` (32-bit float, default) or `PCM_24` with TPDF dither.
  Stems are written the same way and sum to the master (reverb return as its own stem `reverb`).
- No limiting or normalization by default. Options: true-peak limiter (ceiling −1 dBTP, lookahead
  5 ms) and normalization to a LUFS target.

## Report metrics

- Sample peak (dBFS), true peak (dBTP, 4× oversampling, ITU-R BS.1770-4), integrated loudness
  (LUFS, BS.1770 via pyloudnorm), loudness range.
- Per source: id, group, sample, active frame intervals, distance min/max (m), playback rate
  min/max, peak contribution (dBFS), frames with gain above −60 dB, warnings.
- Warnings: rate clamped, source never audible, master sample peak > 0 dBFS (only matters for
  PCM_24), missing or resampled samples, cuts handled.

## Defaults

| Constant | Default | Where set |
|---|---|---|
| Sample rate `fs` | 48000 Hz | scene `sample_rate` |
| Speed of sound `c` | 343.0 m/s | scene `speed_of_sound` |
| Control rate `f_ctl` | 1000 Hz | engine constant |
| Near-field softening `r_min` | 0.25 m | engine constant |
| Retarded-time iterations | 4 | engine constant |
| Playback-rate clamp | [0.25, 4.0] | engine constant |
| Head radius `a` | 0.0875 m | scene `head_radius` |
| ITD scale (hybrid) | 0.5 *(tune)* | scene `itd_scale` |
| Head shadow (hybrid) | 0.5 *(tune)* | scene `head_shadow` |
| `α₈` air absorption at 8 kHz | 0.1 dB/m *(tune)* | engine constant × scene/source `air_absorption` |
| Rear cutoff / gain | 6000 Hz / −2 dB *(tune)* | scene `rear_cutoff_hz`, `rear_gain_db` |
| Occlusion gain / cutoff | −12 dB / 1500 Hz *(tune)* | scene `occlusion_gain_db`, `occlusion_cutoff_hz` |
| Occlusion smoothing | 60 ms / 150 ms *(tune)* | engine constant |
| Reverb send | −18 dB *(tune)* | scene `reverb_send_db`, source `reverb_send_db` |
| Cut crossfade | 10 ms | engine constant |
| Loop seam crossfade | 50 ms | source `loop_crossfade` |

## References

- J. O. Smith, *Physical Audio Signal Processing*, "Doppler Simulation" and "Time-Varying Delay
  Line Reads" (CCRMA).
- J. O. Smith, S. Serafin, J. Abel, D. Berners, "Doppler Simulation and the Leslie", DAFx-02.
- C. P. Brown, R. O. Duda, "A Structural Model for Binaural Sound Synthesis", IEEE Trans. Speech
  and Audio Processing 6(5), 1998 (spherical-head shadow and ITD).
- R. S. Woodworth, *Experimental Psychology*, 1938 (ITD formula).
- ISO 9613-1:1993, attenuation of sound during propagation outdoors, part 1: absorption by the
  atmosphere.
- OpenAL 1.1 specification, distance models and cones.
- ITU-R BS.1770-4, loudness and true-peak measurement; EBU R128.
