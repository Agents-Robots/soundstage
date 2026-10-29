# Spec: signal model

How the engine turns a scene file into audio: frames of reference, time base, the processing
chain per source, the formulas and their defaults. Starting values marked *(tune)* are first
guesses to be adjusted by ear in the phase that introduces them; record the tuned value and the
reason here.

Decisions behind this model: ADR [0006](../adr/0006-propagation-retarded-time-delay-line.md)
(propagation), [0007](../adr/0007-stereo-ear-model.md) (ears and panning),
[0008](../adr/0008-cinematic-air-physics.md) (physics defaults),
[0009](../adr/0009-processing-chain.md) (processing chain and replaceable models),
[0010](../adr/0010-occlusion-fresnel-visibility-box-occluders.md) (occlusion),
[0011](../adr/0011-reverb-efx-presets-synthetic-ir.md) (reverb). Research behind the choices:
[research/](../../research/README.md), one page per model.

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
- Output sample `n` ↔ `t = n / fs`, `fs = sample_rate` (48000 Hz). **Sample 0 = first frame.**
- Output length: `round((frame_end − frame_start + 1) · fs / F)` samples, so the audio ends with
  the last frame's duration.
- Sound emitted before the first frame arrives correctly: reads reach back into emission times
  before `t = 0`, where the dry signal exists too and positions are baked down to
  `t_min = t(frame_start − pad_frames_before)` (held before that, with a warning). The output covers
  `[0, length)` only.

## Processing chain (per source)

```
geometry (control rate 1 kHz, once per source):
  listener p,R(t) and source s(t) splines per segment ─▶ retarded delay τ_c(t) ─▶ path:
  d = c·τ_c, q_ret = Rᵀ(s(t−τ_c) − p), lateral λ, rear ρ, emitter angle β, jumps (cuts, teleports)

emission side (mono, emission rate f_e = f_s · oversample):
  sample ─▶ decode, downmix, resample to f_e, pitch ─▶ dry timeline x(t_e) ─▶ air absorption ─▶ rear low-pass
        ─▶ delay line (emission samples)

reception side (per ear, f_s):
  τ_read,L/R(t) (Doppler factor, sync, ITD, rate clamp) ─▶ fractional-delay read ─▶ occlusion low-pass
        ─▶ head shadow (per ear) ─▶ × gain · g_dist · g_cone · g_rear · G_occ ─▶ × pan gains ─▶ group bus
  centre read (no ITD) ─▶ × send gain ─▶ reverb bus
  at jumps: a second read with the parameters before the jump held, 10 ms equal-power crossfade
```

Emission-side parameters are functions of the path; they are placed on emission time
`t_e = t − τ_read` (made monotonic where a jump makes it go back). The reverb send is taken from
the centre read before panning; occlusion is applied per ear after the read.

All spatial parameters use the **retarded** source position `s(t − τ_c)`: the sound is heard from
where it was emitted, with the loudness of the distance it actually travelled.

Bed sources (`spatial: false`) skip everything between the dry timeline and the group bus except
gain and fades.

## Dry timeline

- Decode with libsndfile (WAV, FLAC, OGG), convert to float64. Spatial sources: multichannel
  samples are downmixed to the mean of their channels (`(L + R) / 2` for stereo). Beds keep the
  first two channels; mono beds go to both channels at −3.01 dB.
- Resample with soxr (VHQ) to the emission rate `f_e` for spatial sources (`2 fs` with the standard
  interpolator, `fs` with the sinc), to `fs` for beds; `pitch` is part of the same ratio
  (`f_e / pitch`).
- **One-shot**: the sample starts at emission time `t_trig = t(frame)`; zero elsewhere. `fade_in`
  as a raised-cosine ramp if set.
- **Loop**: tiled from the loop start (`t(frame)`; if `frame` is null, at every emission time) to
  the loop end (`t(end_frame) + fade_out`, or without end). The seam uses a crossfade of
  `loop_crossfade` seconds (the tail overlaps the head) whose law adapts to the correlation `ρ` of
  head and tail: gains `a, b` with `a² + b² + 2ρab = 1` (equal power for uncorrelated material,
  equal gain for identical material), so the level stays constant across the seam. Start offset
  `loop_phase` seconds into the loop cycle at `t(frame)`, or at `t = 0` (the first frame) when
  `frame` is null; `"random"` = uniform over the cycle, seeded from the source id. Fades are
  raised-cosine.
- The dry timeline is produced on demand for whatever emission times the reads need (before the
  first frame, too).

## Trajectories and control rate

- Baked positions (`substeps` per frame) are interpolated with cubic splines (scipy
  `CubicSpline`, not-a-knot, exact for constant velocity and acceleration) in time, **separately per
  segment** between cuts and per piece between source teleports, and **separately on each side of a
  kink**: a sample where the velocity changes faster than 200 m/s² (about 20 g; keyframed motion
  that starts or stops instantly). A spline through such a kink rings (the playback rate of the
  flyby's ship overshot by 1.8 % where it starts moving); split there, the rate steps cleanly.
  Position stays continuous at a kink, so it is not a jump and gets no crossfade. The listener
  rotation uses scipy's `RotationSpline` per segment (continuous angular rate and acceleration;
  piecewise slerp would step the rate of change of pan and ITD at every baked sample).
- **Jumps.** Listener segments are split at the scene's `cuts` (camera switches) and wherever the
  listener moves faster than `teleport_speed` between two baked samples; source pieces likewise at
  `src_cuts` and at such teleports (default `teleport_speed`: 3 × `speed_of_sound`). A spline is
  evaluated only inside its own segment or piece (held at its ends).
- Geometry is evaluated at the **control rate**, every 48 output samples (1000 Hz at 48 kHz). Delays
  are upsampled from control rate to audio rate with cubic (Catmull-Rom) interpolation (they are
  smooth); gains and filter coefficients are interpolated linearly per sample; nothing is
  interpolated across a jump.

## Propagation: delay, Doppler, ITD

**Retarded time.** For reception time `t` and listener position `p(t)`, the propagation delay
`τ_c(t)` solves `τ = |s(t − τ) − p(t)| / c`. At control rate, two fixed-point steps, then Newton
steps until every point has converged to 1 ns (at most 8):

```
τ⁽⁰⁾ = |s(t) − p(t)| / c
τ ← |s(t − τ) − p(t)| / c                                  (2 fixed-point steps)
f = τ − |s(t − τ) − p(t)| / c,   f' = 1 + u · s'(t − τ) / c,   τ ← τ − f / f'      (Newton)
```

`u` is the unit vector from the listener to the retarded source, `s'` the spline velocity, so
`f' = 1 − v_r / c > 0` for any subsonic motion; the source's piece is chosen by emission time in
every step. Error below 2 ns up to Mach 0.95 ([E07](../../research/experiments/E07-retarded-time.md)).
Where no consistent solution exists (residual above 1 µs: the gap after a source teleports away,
supersonic ambiguity), the source is silent (`audible` false, entered and left with the jump
crossfade). Listener motion needs no iteration (`p` is taken at reception time).

**Doppler factor and picture sync.** With `k = doppler_factor · source.doppler` and `τ₀ = τ_c` at
the source's reference time (one-shot: reception of the trigger; loop: reception of its start
frame, or the first frame of the shot when it has none):

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
are interpolated in log distance. Measured error: within 2.5 dB of ISO 9613-1 wherever the loss is
below 20 dB; beyond that the filter keeps attenuating by more than 17.7 dB
([E05](../../research/experiments/E05-air-absorption.md)). Where the loss at 20 kHz is below
0.05 dB the stage passes the signal unchanged.

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

The bake samples each source's visibility `v_b ∈ [0, 1]` in three bands (250 Hz, 1 kHz, 4 kHz) at
`occlusion_rate` (10 Hz): the open share of five paths through the first Fresnel zone of the path
heard at that time (retarded source, listener at the frame; [model](../../research/models/occlusion.md)).
The engine interpolates `v_b` linearly to the control grid and smooths it per band with an
asymmetric one-pole follower (time constant 60 ms while it falls, 150 ms while it rises). Per band:

```
T(f)  = 10^(occlusion_gain_db / 20) / sqrt(1 + (f / occlusion_cutoff_hz)²)     transmission through occluders
g_b   = v_b + (1 − v_b) · T(f_b)
G     = g_250                                                                  broadband gain
f_occ = argmin over f_c of Σ_{b = 1k, 4k} (20 log₁₀(g_b / G) + 10 log₁₀(1 + (f_b / f_c)²))²
```

`f_occ` is the one-pole cutoff whose attenuation best matches the upper bands in dB (least squares,
by bisection on `1/f_c²`; ∞ where nothing is attenuated). Fully occluded, `G = T(250)` and
`f_occ` = 1528 Hz reproduce `T(f)` within 0.12 dB up to 4 kHz. `G` multiplies the source gain;
`f_occ` drives a TPT one-pole per ear, after the read and before head shadow. Both apply to the
direct sound; the reverb send gets them only with `occlusion_mode = "occlusion"`.

All low-passes are one-poles in TPT (zero-delay feedback) form: `g = tan(π f_c / f_e)`,
`G = g / (1 + g)`, per sample `v = G (x − s)`, `y = v + s`, `s = y + v`. `G` is computed at control
rate and interpolated linearly per sample; it stays in (0, 1), so every intermediate filter is
stable and modulation does not zipper.

## Reverb send

Each spatial source feeds a mono send, read from its delay line with the centre delay (no ITD), so
air absorption and the rear low-pass (emission side) are in it, but not pan, head shadow or the rear
gain ([model](../../research/models/reverb.md)):

```
send = 10^((gain_db + reverb_send_db_source + reverb_send_db_scene) / 20)
       · g_dist(d; distance_model, ref_distance, max_distance, rolloff = room_rolloff) · g_cone · y_c
       (· G_occ and the occlusion low-pass, in occlusion mode)
```

`reverb_send_db_source` is 0 when null; `room_rolloff` is `reverb_room_rolloff`, or the preset's
room rolloff factor (0 for nearly all presets: the reverberant level does not fall with distance,
so the direct-to-reverberant ratio falls 6 dB per doubling). Beds send only with an explicit
`reverb_send_db`, taken from their stereo mix.

The sum of all sends is convolved once per chunk (FFT overlap-add, tail carried to the next chunk)
with a stereo impulse response:

- **EFX preset** (`reverb` = a name from `soundstage presets`): synthesized, seeded by the name.
  Early reflections: `8 + 16 · density` sparse ±1 taps per channel between `reflections_delay` and
  `reflections_delay + late_reverb_delay`, decaying by e⁻³ across that span. Late tail from
  `reflections_delay + late_reverb_delay`: noise (Gaussian, or velvet noise with
  `300 + 3700 · diffusion²` pulses/s when `diffusion` < 0.99), split into complementary 1/3-octave
  bands from 20 Hz (raised-cosine crossfades on a log-frequency axis, summing to 1), each band times
  `exp(−3 ln 10 · t / T60(f_c))`, with
  `1/T60(f) = 1/T_m + (1/T_l − 1/T_m) / (1 + (f/f_l)⁴) + (1/T_h − 1/T_m) · (f/f_h)⁴ / (1 + (f/f_h)⁴)`,
  `T_m = decay_time`, `T_l = T_m · decay_lf_ratio`, `T_h = T_m · decay_hf_ratio` (limited to
  `60 / (−20 log₁₀(air_absorption_gain_hf) · 343)` when `decay_hf_limit`), `f_l = lf_reference`,
  `f_h = hf_reference`; 5 ms fade-in. Section energies per channel: `(gain · reflections_gain)²` and
  `(gain · late_reverb_gain)²`. Then first-order shelves: `gain_hf` above `hf_reference`, `gain_lf`
  below `lf_reference`. Length `late start + 1.1 · max(T)`, at most 15 s.
- **File** (`reverb` = a path): WAV, FLAC, OGG or AIFF, resampled to `fs`, mono duplicated to
  stereo (first two channels of multichannel files), used as recorded (no normalization); room
  rolloff 0 unless `reverb_room_rolloff` is set.

The reverb return is added to the master and is its own stem `reverb`. **Pre-roll**: the sends of
the impulse response's length before the first output sample (at most the baked padding) are
rendered and fed to the bus, and only its output is discarded, so sound already playing at the
start of the render (or of a `--frames` sub-range) has its reverberation from the first sample.

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
  `g = gain · g_dist · g_cone · g_rear · G_occ` and pan gains applied per channel.
- Master = Σ groups + reverb return, times `master_gain_db`. Stems are the group buses and the
  reverb return, kept as float32; they sum to the master (to about 1e-7).
- Off by default (final mixing happens in Resolve), in this order when requested
  ([model](../../research/models/mixing-and-loudness.md)):
  1. `--normalize LUFS`: one gain that brings the integrated loudness (BS.1770, pyloudnorm) to the
     target.
  2. `--limit DBTP`: offline true-peak limiter. Needed gain per sample `min(1, ceiling / tp)` from the
     8× oversampled true peak; sliding minimum over ±5 ms (look-ahead), then a moving average over
     5 ms, then release `level += (g − level)(1 − e^(−1/(0.08 s · fs)))` where the gain rises
     (instant fall); up to four passes until the 8× true peak is at the ceiling.
  The same gains are applied to the stems.
- Output: WAV via libsndfile, `FLOAT` (32-bit float, default) or `PCM_24` with TPDF dither.

## Culling

Shots with many sources skip what does not matter, within an error budget `cull_db` (−40 dB; null
turns culling off and the render is the full one, bit for bit). The rule
([model](../../research/models/culling.md), measured in
[E16](../../research/experiments/E16-culling.md)), per group and per decision block:

```
E_i            estimated energy of entry i in the block
skip the quietest entries while   Σ_skipped E_i  ≤  10^(cull_db / 10) · Σ_group E_i
```

The budget bounds the summed error of everything skipped, however many quiet sources add up (a
per-source threshold does not). Each group has its own budget, so a stem played alone keeps its
accuracy; beds count towards their group's total and are never skipped. Ties go by source order, so
renders stay deterministic (NFR-2).

**Render.** Decision blocks are 0.4 s (the momentary-loudness window); the render works in 4 s
chunks, and a voice skips a chunk when every block of it allows that.

1. Before setup, an upper bound per source and block from the baked positions: the straight-line
   distance at every baked sample, mapped to its reception time `t + d/c`;
   `E ≤ 10^(gain_db/10) · g_dist(d)² · max(1, g_rear²) · ms_peak · T`, plus the reverb send with the
   room rolloff, where `ms_peak` is the sample's highest 10 ms mean square and `T` the block length
   (one-shots only while they sound). Cone, occlusion, pan and filters only lower it. Group totals
   use the sample's mean square instead. Sources skipped in every block 20 dB below the budget
   (`BOUND_MARGIN_DB`) are not set up at all.
2. After setup, per voice (one-shots with one renderer per trigger count per trigger): the gains on
   the control grid, the share of the sample's power each path's filters pass, and the dry signal's
   mean square around the emission time, per control point and widened by one control point:

   ```
   P = (g_L² F_L + g_R² F_R + g_send² F_send) · ms_dry(t − τ)
   F_x = Σ_b w_b · Π_stages |H(p · f_b)|²
   ```

   `w_b` and `f_b` are the power shares and power-weighted centre frequencies of the sample's
   1/3-octave bands (mono downmix, at its own rate), `p` the pitch; the product runs over the
   path's filters (air absorption and rear cue on the emission side, then occlusion low-pass and
   head shadow per ear; the send's occlusion low-pass) with their parameters at that control
   point, evaluated every 16 control points and interpolated in between. `ms_dry` comes from 1 ms
   block sums of the sample or loop cycle before the interpolator's prefilter.
3. A skipped chunk is not rendered. Leaving a rendered chunk, the voice renders the first 10 ms of
   the skipped one with a raised-cosine fade-out; before a rendered chunk, the last 10 ms with a
   fade-in. A voice that resumes rebuilds its delay line and clears its filter states 50 ms before
   that (warm-up), so the rendered chunks match the full render (to 1e-9 in the tests).

**Bake.** At every visibility sample, the same estimate from the distance of the sound heard then
(retarded positions), the gain, distance law and the sample's level (read with Blender's `aud`),
one-shots while they sound (±0.5 s); the rule skips the visibility rays of the quietest occluding
sources 20 dB below `cull_db`. Skipped samples get the visibility interpolated from the source's
computed samples (open where none was computed); the manifest records the skipped share
(`occlusion.culled_share`).

## Report metrics

- Master and each group (stem): sample peak (dBFS), true peak (dBTP, ITU-R BS.1770-4: 4×
  oversampled through a Kaiser low-pass with 32 taps per phase, β 8), integrated loudness (LUFS,
  pyloudnorm), loudness range (LU, EBU Tech 3342: 3 s windows every 0.1 s, K-weighted, gated at
  −70 LUFS and 20 LU below the mean, 95th minus 10th percentile).
- Per source: id, group, sample, active frame range, distance min/max (m), delay min/max (ms),
  playback rate min/max, peak contribution (dBFS, with the master gain), frames with peak above
  −60 dBFS, and with visibility: its range (mean over bands, per frame) and the frames below 0.5;
  with culling, the seconds during which the source was skipped (`culled_s`).
- `culling`: the budget, sources, sources skipped before setup and skipped entirely, and the share
  of voice time rendered.
- `reverb`: the environment's name; `processing`: normalization gain, limiter's maximum reduction
  and active time.
- Warnings: those of the bake, then rate clamped, source never audible (except sources culling
  skipped entirely), sound emitted before the baked range, Phase 4 keys ignored, bake settings
  given with `--set`, an empty selection ([cli.md](cli.md#report-mixreportjson)).

## Tuning (Phase 2, #15)

The Phase 2 starting values were judged by ear on the flyby and a 115-source real shot, on
headphones and loudspeakers, against the `power` pan law and a render without Doppler or ear model.
Both pan laws sounded right; `sine` stays the default because it is the standard constant-power
sin/cos law of mixing consoles, DAWs and OpenAL Soft. ITD 0.5, head shadow 0.5 and the rear cue
(6 kHz, −2 dB) were kept. Values marked *(tune)* below belong to Phase 3 and are still to be judged
by ear.

## Defaults

| Constant | Default | Where set |
|---|---|---|
| Sample rate `fs` | 48000 Hz | scene `sample_rate` |
| Speed of sound `c` | 343.0 m/s | scene `speed_of_sound` |
| Control rate `f_ctl` | every 48 output samples (1000 Hz at 48 kHz) | engine constant `CONTROL_STEP` |
| Near-field softening `r_min` | 0.25 m | engine constant |
| Retarded-time solver | 2 fixed-point steps, then Newton to 1 ns (at most 8 steps) | engine constants |
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
| Occlusion transmission | −12 dB, low-pass 1500 Hz *(tune)* | scene `occlusion_gain_db`, `occlusion_cutoff_hz` |
| Occlusion smoothing | 60 ms falling / 150 ms rising *(tune)* | engine constants `OCCLUSION_ATTACK_S`, `OCCLUSION_RELEASE_S` |
| Visibility | 10 Hz, bands 250 / 1000 / 4000 Hz, 4 points each + direct path | scene `occlusion_rate`; bake constants |
| Occluders | bounding boxes ≥ 2 m diagonal | scene `occluder_min_size`; object `sfx_occluder` |
| Source size for visibility | 0.25 m | source `occlusion_radius` |
| Reverb | none; send 0 dB, room rolloff from the preset | scene `reverb`, `reverb_send_db`, `reverb_room_rolloff`; source `reverb_send_db` |
| Limiter | look-ahead 5 ms, release 80 ms, 8× true peak | `mix.true_peak_limiter` |
| Instances per tagged object | 32 closest | scene `instance_limit` |
| Cut crossfade | 10 ms | engine constant |
| Loop seam crossfade | 50 ms, correlation-adaptive | source `loop_crossfade` |
| Culling | budget −40 dB per group; 0.4 s decision blocks, 4 s chunks; upper bounds 20 dB below; fades 10 ms, warm-up 50 ms | scene `cull_db`; engine constants `cull.BLOCK_S`, `render.CHUNK_BLOCKS`, `levels.BOUND_MARGIN_DB`, `render.CULL_FADE_S`, `source.WARMUP_S` |

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
- ITU-R BS.1770-4, loudness and true-peak measurement; EBU R128; EBU Tech 3341 (loudness meter
  test signals), EBU Tech 3342 (loudness range).
- N. Tsingos, J.-D. Gascuel, "Soundtracks for Computer Animation: Sound Rendering in Dynamic
  Environments with Occlusions", Graphics Interface 1997 (Fresnel-zone visibility).
- EFX reverb presets (OpenAL Soft `efx-presets.h`); J. A. Moorer, "About This Reverberation
  Business", 1979 (decaying noise); V. Välimäki et al., "Late Reverberation Synthesis Using
  Filtered Velvet Noise", 2017.
