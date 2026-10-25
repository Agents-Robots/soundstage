# Roadmap

Phases, their scope and when each counts as done. Requirement IDs refer to
[requirements.md](requirements.md). Progress, tasks and open questions live in the issue tracker,
not here.

Each phase ends with a render of the synthetic flyby scene and one real shot from a user project,
listened to by the user in Resolve.

## Phase 0: baseline spike (½ day)

Find out what Blender's built-in Speaker objects and mixdown give, headless, so there is a
reference to beat and a confirmed list of what they lack.

- Script-built test scene: camera on a line, a speaker with a sine or engine loop flying past, a
  one-shot speaker at a known frame.
- `bpy.ops.sound.mixdown` from `blender -b`; note whether it works headless, what context it
  needs, and how distance, pan and Doppler sound.
- Also check: lists of dicts as ID properties in Blender 5.2 (tag storage, see
  [spec/tagging.md](spec/tagging.md)).

Done when: a mixdown WAV exists (or the failure is understood), findings are in
[research.md](research.md), and the ID-property question is answered.

## Phase 1: MVP, the minimum requirements

Placed sound with distance and side, frame-exact, end to end.

- `schema.py`, `tag.py` (FR-1–5), `bake.py` per frame (FR-20, 21, 26–28).
- Engine: scene loading, samples (resample, downmix), loops and one-shots with fades (FR-3, 50),
  distance gain (FR-40), constant-power pan (FR-41), no delay yet.
- Output WAV float/PCM24 aligned to the first frame (FR-60, 61), basic report (FR-63), partial
  renders and solo/mute (FR-67), preview mux (FR-66).
- CLI: `bake`, `inspect`, `render`, `preview`.
- Test samples generator, synthetic flyby fixture, unit tests for gain, pan, alignment, loop seam.

Done when:
- known-answer tests pass: −6.02 dB ± 0.1 dB at 2× `ref_distance`; `g_L² + g_R²` constant
  across a pan sweep; a one-shot at frame 120 at 30 fps starts at sample 190 400 ± 1 (frame_start 1);
  output length matches the shot at 24, 25, 30 and 29.97 fps;
- the flyby scene bakes and renders headless with one command each;
- the user has listened to a real shot in Resolve and agrees placement and loudness are right.

## Phase 2: physics

Doppler, delay and the ear model.

- Bake: sub-frames (FR-22), padding (FR-23), camera switches and jump detection (FR-24), forward
  vectors, offsets (FR-6).
- Engine: splines and control rate, retarded time, Doppler factor, picture sync (FR-42, 43), ITD
  and head shadow in the hybrid panner (FR-44), air absorption (FR-45), rear cue (FR-46), cones
  (FR-7), cut crossfades (FR-49), playback-rate clamp (FR-51), cubic and sinc reads; numba kernels
  with numpy references.
- Performance target NFR-3 met.

Done when:
- a source at 343 m is heard 1.000 s ± 1 sample late;
- a 1 kHz source passing at 34.3 m/s measures 1111 Hz approaching and 909 Hz receding (± 0.5 %),
  and a camera moving past a static source at the same speed gives 1100 Hz / 900 Hz;
- ITD at 90° equals 0.656 ms × `itd_scale` (± 1 sample at 4× oversampling);
- no sample step above the bound when a source passes through the camera or across a cut;
- 50 sources × 5 min render in ≤ 5 min on a current desktop CPU;
- the user has judged the Doppler and the ear model on a real shot and the *(tune)* values in
  [spec/signal-model.md](spec/signal-model.md) are updated.

## Phase 3: environment and mixing

- Bake: visibility by ray casting (FR-25), Speaker objects as sources (FR-8), collection instances
  (FR-9).
- Engine: occlusion (FR-47), reverb send with synthetic presets and IR files (FR-48), stems
  (FR-62), full report with LUFS and true peak (FR-63), normalization and limiter (FR-64), debug
  plot (FR-65).
- Short guide for agents that build scenes: how to tag sounds in generator scripts.

Done when:
- a source moving behind an occluder drops by `occlusion_gain_db` with its spectrum low-passed,
  smoothly (no step above the bound);
- stems sum to the master within float rounding;
- the report's LUFS matches pyloudnorm on the written file, true peak within 0.1 dB of a 4×
  oversampled reference;
- the user has used the stems in Fairlight on a real shot.

## Phase 4: options (by need)

Picked when a shot needs them, in any order:

- Binaural output from SOFA HRTFs (FR-52).
- AmbiX ambisonic output (FR-53), after testing Fairlight's import conventions.
- Random variation of one-shots (FR-54).
- Animated parameters via keyframed custom properties (FR-10).
- Culling and grouping for shots with hundreds of sources (traffic, fleets).
- BWF timecode in the output for automatic placement in Resolve.

Each item gets its own acceptance criteria in its ticket when picked.
