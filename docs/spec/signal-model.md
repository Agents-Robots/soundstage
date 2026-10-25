# Spec: signal model

How the engine turns a scene file into audio: frames of reference, time base, the processing
chain per source, the formulas and their defaults. Starting values marked *(tune)* are first
guesses to be adjusted by ear in the phase that introduces them; record the tuned value and the
reason here.

Decisions behind this model: ADR [0006](../adr/0006-propagation-retarded-time-delay-line.md)
(propagation), [0007](../adr/0007-stereo-ear-model.md) (ears and panning),
[0008](../adr/0008-cinematic-air-physics.md) (physics defaults),
[0009](../adr/0009-processing-chain.md) (processing chain and replaceable models). Research behind
the Phase 2 choices: [research/](../../research/README.md), one page per model.

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
geometry (control rate 1 kHz, once per source):
  listener p,R(t) and source s(t) splines per segment ─▶ retarded delay τ_c(t) ─▶ path:
  d = c·τ_c, q_ret = Rᵀ(s(t−τ_c) − p), lateral λ, rear ρ, emitter angle β, jumps (cuts, teleports)

emission side (mono, emission rate f_e = f_s · oversample):
  sample ─▶ decode, downmix, resample to f_e, pitch ─▶ dry timeline x(t_e) ─▶ air absorption ─▶ rear low-pass
        ─▶ delay line (emission samples)

reception side (per ear, f_s):
  τ_read,L/R(t) (Doppler factor, sync, ITD, rate clamp) ─▶ fractional-delay read ─▶ head shadow (per ear)
        ─▶ × gain · g_dist · g_cone · g_rear ─▶ × pan gains ─▶ group bus
  at jumps: a second read with the parameters before the jump held, 10 ms equal-power crossfade
```

Emission-side parameters are functions of the path; they are placed on emission time
`t_e = t − τ_read` (made monotonic where a jump makes it go back). The reverb send (Phase 3) is
taken from the centre read before panning.

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
  (`t(end_frame) + fade_out`, or the end of the simulated range). The seam uses a crossfade of
  `loop_crossfade` seconds (the tail overlaps the head) whose law adapts to the correlation `ρ` of
  head and tail: gains `a, b` with `a² + b² + 2ρab = 1` (equal power for uncorrelated material,
  equal gain for identical material), so the level stays constant across the seam. Start offset `loop_phase`
  seconds into the sample; `"random"` = uniform in [0, sample length), seeded from the source id.
  Fades are raised-cosine.
- The dry timeline covers emission times from `t_min − max delay` to the end, so every read
  position exists.

## Trajectories and control rate

- Baked positions (`substeps` per frame) are interpolated with cubic splines (scipy
  `CubicSpline`, not-a-knot, exact for constant velocity and acceleration) in time, **separately per
  segment** between cuts and per piece between source teleports, and **separately on each side of a
  kink**: a sample where the velocity changes faster than 200 m/s² (about 20 g; keyframed motion
  that starts or stops instantly). A spline through such a kink rings (the playback rate of the
  flyby's ship overshot by 1.8 % where it starts moving); split there, the rate steps cleanly.
  Position stays continuous at a kink, so it is not a jump and gets no crossfade. The listener rotation uses scipy's `RotationSpline` per segment (continuous
  angular rate and acceleration; piecewise slerp would step the rate of change of pan and ITD at
  every baked sample).
- **Jumps.** Listener segments are split at the scene's `cuts` (camera switches) and wherever the
  listener moves faster than `teleport_speed` between two baked samples; source pieces likewise at
  `src_cuts` and at such teleports (default `teleport_speed`: 3 × `speed_of_sound`). A spline is
  evaluated only inside its own segment or piece (held at its ends).
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

**Voices.** A one-shot with several trigger frames is rendered as one voice per trigger when
`sync_to_picture` is set or `k ≠ 1`, so each trigger has its own `τ₀`; otherwise as one voice.

**Delays at audio rate.** `τ_read,e` is interpolated from the control rate with a cubic
(Catmull-Rom) curve; the read position in the delay line is `(t − τ_read,e(t)) · f_e`.

**Fractional-delay read.** `y_e(t) = x(t − τ_read,e(t))`, read at fractional sample positions
(interpolator registry, chosen by `quality`):

- `quality = "standard"` (`optimal2x`): the dry signal is built at `f_e = 2 f_s` (samples
  resampled once by soxr), pre-emphasized by a 63-tap symmetric FIR that flattens the
  interpolator's passband, and read with Niemitalo's 6-point, 5th-order polynomial optimized for 2×
  oversampled input. Read error below −90 dB up to 18 kHz. Reading faster than about 1.09× real time folds content
  above 22 kHz back below 24 kHz.
- `quality = "high"` (`sinc`): `f_e = f_s`; Kaiser-windowed sinc (β = 9, 16 zero crossings per
  side, table with linear interpolation) with the cutoff `0.92 · f_s/2 · min(1, 1/rate)` and the
  kernel widened accordingly, which band-limits when reading faster than real time.
- `hermite4` (4-point cubic Hermite at `f_e = f_s`) is kept as a reference in tests only.

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

Pure-tone attenuation coefficient `α(f)` in dB/m from ISO 9613-1 (oxygen and nitrogen
relaxation), at `air_temperature_c` (20 °C), `air_humidity_pct` (50 %) and standard pressure,
scaled by `A = air_absorption · source.air_absorption`. The loss over the propagation distance `d`
is `A · α(f) · d` dB. At 20 °C, 50 % RH: about 0.005 dB/m at 1 kHz, 0.03 at 4 kHz, 0.1 at 8 kHz.

Realization: four cascaded one-pole low-passes (TPT form) on the emission side. Their cutoffs are
fitted once per render, by least squares on the loss in dB from 100 Hz to 20 kHz where the target
loss is below 20 dB, on a log-spaced grid of effective distances `A·d` from 5 cm to 20 km
(continuation from the previous grid point keeps the cutoffs smooth); at control rate the cutoffs
are interpolated in log distance. Measured error: within about 2 dB of ISO 9613-1 wherever the loss
is below 20 dB; beyond that the filter keeps attenuating more than 18 dB. Where the loss at 20 kHz
is below 0.05 dB the stage passes the signal unchanged.

## Panning

**`amplitude`**: constant-power pan from the lateral sine only, by the pan law `pan_law`:

```
sine  (default):  φ = (λ + 1) · π / 4,   g_L = cos φ,   g_R = sin φ
power:            g_L = sqrt((1 − λ) / 2),   g_R = sqrt((1 + λ) / 2)      (Blender's speakers, Phase 0)
```

Both keep `g_L² + g_R² = 1` (centre −3.01 dB each). `power` is softer at the sides (−18 dB for
the far channel at 76°, against −32 dB for `sine`).

**`hybrid`** (default): the amplitude pan above, plus ITD scaled by `itd_scale` (default 0.5,
tuned: full ITD across speakers causes comb filtering in mono downmixes), plus a head-shadow
filter per ear scaled by `head_shadow` (default 0.5, tuned).

Head shadow (Brown & Duda 1998 spherical-head model), per ear, with `θ_e` the angle between that
ear's axis (+X for right, −X for left) and the source direction (`cos θ_R = λ`, `cos θ_L = −λ`):

```
α(θ) = (1 + α_min/2) + (1 − α_min/2) · cos(θ · 180° / θ_min),   α_min = 0.1, θ_min = 150°
α_eff = 1 + head_shadow · (α(θ) − 1)
H(ω) = (1 + j · α_eff · ω / (2ω₀)) / (1 + j · ω / (2ω₀)),   ω₀ = c / a
```

a first-order shelf (up to +6 dB treble at the near ear, down to −20 dB at the far ear at full
strength), discretized with the bilinear transform prewarped at the pole `2ω₀` (1.25 kHz for
`a = 8.75 cm`). The pole does not depend on `α`, so only the numerator coefficients change; they
are interpolated per sample between control points, which is exact and always stable.

**`binaural`** (Phase 4): replaces pan, ITD and head shadow with HRIR convolution from a SOFA set,
interpolated between measured directions.

## Rear cue

Stereo cannot place a source behind the camera, so behind is marked spectrally and by level
(hybrid panner), with the rear factor `ρ`:

```
y = x + ρ · (LP(x) − x)          LP: one-pole low-pass at rear_cutoff_hz (emission side)
g_rear = 10 ^ (rear_gain_db · ρ / 20)
```

The low-pass mixed with the dry signal is a first-order high-frequency shelf whose depth grows with
`ρ`: transparent in front and at the side, the plain low-pass straight behind. (A low-pass whose
cutoff moves to 20 kHz at the side would still take 1–2 dB off 15 kHz for every source.)

## Occlusion

Visibility `v ∈ [0, 1]` from the bake (fraction of unobstructed rays from the camera to points
within `occlusion_radius` of the emitter) is smoothed with a one-pole follower (60 ms when
becoming occluded, 150 ms when becoming visible, *(tune)*), then:

```
g_occ = 10 ^ ((1 − v) · occlusion_gain_db / 20)                     occlusion_gain_db = −12 (tune)
f_occ = 20000 · (occlusion_cutoff_hz / 20000) ^ (1 − v)             occlusion_cutoff_hz = 1500 (tune)
```

Occlusion gets its own low-pass stage (Phase 3); air absorption and the rear cue are separate
stages. All low-passes are one-poles in TPT (zero-delay feedback) form: `g = tan(π f_c / f_e)`,
`G = g / (1 + g)`, per sample `v = G (x − s)`, `y = v + s`, `s = y + v`. `G` is computed at control
rate and interpolated linearly per sample; it stays in (0, 1), so every intermediate filter is
stable and modulation does not zipper.

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

- **Listener cuts** (camera switches from the bake, listener jumps detected by speed) split
  reception time into segments. Each segment uses its own listener trajectory (splines never cross
  a cut). The output around a cut is an equal-power crossfade of 10 ms between a second read with
  every parameter held at its value before the cut (delays, gains, pan, filters) and the new read.
  There is no Doppler sweep across the cut.
- **Source teleports** (`src_cuts` and jumps detected by speed): the source trajectory is
  piecewise; `s(t_e)` is evaluated in the piece that contains the emission time, so sound emitted
  before the jump still comes from the old place. Where the piece changes in reception time, the
  same 10 ms crossfade applies.

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

## Tuning (Phase 2, #15)

The Phase 2 starting values were judged by ear on the flyby and a 115-source real shot, on
headphones and loudspeakers, against the `power` pan law and a render without Doppler or ear model.
Both pan laws sounded right; `sine` stays the default because it is the standard constant-power
sin/cos law of mixing consoles, DAWs and OpenAL Soft. ITD 0.5, head shadow 0.5 and the rear cue
(6 kHz, −2 dB) were kept. Values marked *(tune)* below belong to Phase 3 and are still to be judged.

## Defaults

| Constant | Default | Where set |
|---|---|---|
| Sample rate `fs` | 48000 Hz | scene `sample_rate` |
| Speed of sound `c` | 343.0 m/s | scene `speed_of_sound` |
| Control rate `f_ctl` | 1000 Hz | engine constant |
| Near-field softening `r_min` | 0.25 m | engine constant |
| Retarded-time iterations | 4 | engine constant |
| Playback-rate clamp | [0.25, 4.0] | engine constant |
| Teleport speed | 3 × speed of sound | scene `teleport_speed` |
| Interpolator | `optimal2x` (standard), `sinc` (high) | scene `quality` |
| Pan law | `sine` (tuned) | scene `pan_law` |
| Air temperature / humidity | 20 °C / 50 % | scene `air_temperature_c`, `air_humidity_pct` |
| Head radius `a` | 0.0875 m | scene `head_radius` |
| ITD scale (hybrid) | 0.5 (tuned) | scene `itd_scale` |
| Head shadow (hybrid) | 0.5 (tuned) | scene `head_shadow` |
| Air absorption scale | 1 (ISO 9613-1) | scene/source `air_absorption` |
| Rear cutoff / gain | 6000 Hz / −2 dB (tuned) | scene `rear_cutoff_hz`, `rear_gain_db` |
| Occlusion gain / cutoff | −12 dB / 1500 Hz *(tune)* | scene `occlusion_gain_db`, `occlusion_cutoff_hz` |
| Occlusion smoothing | 60 ms / 150 ms *(tune)* | engine constant |
| Reverb send | −18 dB *(tune)* | scene `reverb_send_db`, source `reverb_send_db` |
| Cut crossfade | 10 ms | engine constant |
| Loop seam crossfade | 50 ms, correlation-adaptive | source `loop_crossfade` |

## References

- J. O. Smith, *Physical Audio Signal Processing*, "Doppler Simulation" and "Time-Varying Delay
  Line Reads" (CCRMA).
- J. O. Smith, S. Serafin, J. Abel, D. Berners, "Doppler Simulation and the Leslie", DAFx-02.
- C. P. Brown, R. O. Duda, "A Structural Model for Binaural Sound Synthesis", IEEE Trans. Speech
  and Audio Processing 6(5), 1998 (spherical-head shadow and ITD).
- R. S. Woodworth, *Experimental Psychology*, 1938 (ITD formula).
- ISO 9613-1:1993, attenuation of sound during propagation outdoors, part 1: absorption by the
  atmosphere.
- O. Niemitalo, *Polynomial Interpolators for High-Quality Resampling of Oversampled Audio*, 2001.
- V. Zavalishin, *Preserving the LTI system topology in s- to z-plane transforms*, 2008.
- OpenAL 1.1 specification, distance models and cones.
- ITU-R BS.1770-4, loudness and true-peak measurement; EBU R128.
