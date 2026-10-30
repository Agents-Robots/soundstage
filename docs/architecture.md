# Architecture

How `soundstage` is built and why. Exact formats and formulas are in [spec/](spec/); the
decisions behind the structure are in [adr/](adr/README.md).

## Pipeline

```
┌──────────────────────────── Blender (bpy, headless) ────────────────────────────────┐
│ generator scripts ──▶ tag.add_sound(obj, …) ──▶ obj["sfx"], scene["sfx_settings"]   │
│ hand-made scenes  ──▶ Speaker objects (+ sfx_speaker), tags in instanced assets     │
│                                                    │                                │
│ bake.py: collect sources (emitters.py), step frames + sub-frames, record listener   │
│          and sources, visibility per band (occlusion.py), detect cuts               │
│          ──▶ scene.json + scene.npz                                                 │
└──────────────────────────────────────────────────────┬──────────────────────────────┘
                                                       │ files (versioned contract)
┌──────────────────────────── engine (venv: numpy, scipy, numba) ─────────────────────┐
│ scene.py      load + validate + resolve settings (--set)                            │
│ signals.py    samples → dry timelines (resample, pitch, loops, one-shots, fades)    │
│ geometry.py   splines per segment, retarded time, control-rate paths (control.py)   │
│ propagation.py Doppler/sync/ITD read delays, interpolators, delay line              │
│ filters.py    distance gain, cone, air absorption, rear cue, occlusion, head shadow │
│ panning.py    amplitude / hybrid (binaural later); kernels.py numba loops           │
│ source.py     the processing chain of one source (emission → delay line → ears)     │
│ farfield.py   sources beyond detail_voices: shared buffers, distance-band buses      │
│ reverb.py     EFX presets → synthetic IR, or IR file; send bus convolution          │
│ render.py     orchestrates per source and per chunk; group buses, reverb bus        │
│ mix.py        normalize, true-peak limiter, stems, WAV writing                      │
│ report.py     metrics per master/group/source, warnings; plot.py debug plot         │
└──────────────────────────────────────────────────────┬──────────────────────────────┘
                                                       ▼
                         mix.wav, stems, report.json, plot.png ──▶ Resolve / agent checks
```

## Why two halves

- **Blender knows where things are; it is a poor place to do DSP.** Positions, camera switches,
  parenting, constraints, drivers and geometry for ray casts all live in Blender, and the
  depsgraph evaluates them exactly as the render does. DSP needs numpy/scipy/numba, fast
  iteration, and tests that run without Blender. So Blender exports, and a normal Python program
  renders. (ADR [0001](adr/0001-standalone-engine-with-blender-bake.md))
- **The scene file is the seam.** Re-rendering with other settings (Doppler strength, panner,
  solo a source) does not touch Blender. Tests write scene files directly. Bake and engine can
  evolve separately as long as the format version is respected.
  (ADR [0004](adr/0004-scene-interchange-json-npz.md))
- **Blender-side code has no extra dependencies**, so it runs in any Blender with
  `--factory-startup` and nothing to install (no add-on to register).

## Modules

### `soundstage/blender/`

| Module | Responsibility |
|---|---|
| `tag.py` | Public helper for generator scripts: add, clear, list sound tags; scene settings; validation of keys and types against the schema. `bpy` and stdlib only. |
| `bake.py` | Script run with `blender -b … --python bake.py -- <args>`. Collects and validates the sources, resolves the listener per frame, steps through frames and sub-frames (`scene.frame_set(f, subframe=s)`), reads evaluated world matrices and the camera's frame edges (`view_frame`: lens, sensor fit, aspect, shift) from the depsgraph, applies tag offsets, samples visibility at `occlusion_rate`, detects cuts, resolves sample paths and defaults, writes the scene file. Uses Blender's bundled numpy. |
| `emitters.py` | Where sources come from: tags on view-layer objects, Speaker objects (mapped to tag entries, packed sounds written out), tags inside collection and geometry-nodes instances (one source per instance, the closest `instance_limit`); each source's world matrix per sample. |
| `occlusion.py` | Occluders (oriented bounding boxes of the connected parts of rendered meshes in a BVH, light-only materials and the listener's vehicle left out, moving ones per sample at their retarded positions (instances rigid with their instancer by its matrix), `sfx_occluder` overrides), Fresnel-zone points per band, visibility per source with the containment and reflector rules ([model](../research/models/occlusion.md)). |
| `scan.py` | Script run like `bake.py`: samples the shot at evenly spaced frames and writes a JSON list of cameras, moving objects and static objects near the camera, so an agent can choose sound sources. |
| `util.py` | Shared helpers for `bake.py` and `scan.py`: argument handling, running `--run` scripts, frame stepping, output prefix for the CLI. |
| `schema.py` | The tag and settings schema (keys, types, defaults, ranges) as plain data, shared by `tag.py`, `bake.py` and the engine, so defaults exist in one place (NFR-8). Stdlib only. |
| `cull.py` | Culling and level of detail in the bake: per visibility sample, which occluding sources may be heard (level estimate from distance, gain and the sample's level read with `aud`) and which rank beyond 2 × `detail_voices` in their group (direct path only); fills the skipped visibility samples by interpolation. |

### `soundstage/levels.py`

Shared by both halves (numpy only): the distance models and the culling rule `skip_mask` (per
group, skip the quietest entries while their summed energy stays within the budget).

### `soundstage/engine/`

| Module | Responsibility |
|---|---|
| `scene.py` | Load `scene.json` + `scene.npz`, check format/version, apply `--set` overrides and resolve the settings (a dict), build the `Scene` and `Source` dataclasses; `build_manifest` and `write_scene` for tests and hand-made scenes. |
| `signals.py` | Decode and cache samples (soundfile), downmix, resample (soxr) to the emission rate, pitch; `DryGenerator` builds each source's dry timeline window by window over emission time: loop tiling with seam crossfade and seeded phase, one-shot placement, fades; sample levels, band spectra and the dry signal's energy over intervals, for culling. |
| `control.py` | The control grid (1 kHz) and interpolation of control-rate tracks to audio samples (linear for gains and filter parameters, Catmull-Rom for delays), never across a jump. |
| `geometry.py` | Tracks: positions as cubic splines per piece (split at cuts and detected teleports), listener rotation as `RotationSpline` per segment; retarded-time solver (fixed point + Newton, audibility mask); the per-source `Path` on the control grid; camera-space vectors and derived angles (with `pan_reference = "screen"` the lateral sine through the lens, from the baked frame edges). |
| `propagation.py` | Read delays per ear (Doppler factor, picture sync, ITD, playback-rate clamp per run between jumps); interpolator registry (`optimal2x`, `sinc`, `hermite4`); the `DelayLine` of emission samples. |
| `filters.py` | Gain laws (distance models, cone, rear), ISO 9613-1 air absorption and its fitted state-variable sections, Brown–Duda head-shadow coefficients, occlusion gain and fitted cutoff from visibility; stages `OnePoleStage`, `RearStage` (emission side), `GridOnePoleStage` (occlusion) and `ShelfStage` (per ear), each with its power response at control points for the culling estimate. |
| `panning.py` | Pan-law registry (`sine`, `power`) and panner registry (`amplitude`, `hybrid`): per-ear delays (ITD), per-ear stages and pan gains from the path; later `binaural`. The screen-relative mapping of the lateral sine (`screen_lateral`). |
| `kernels.py` | All per-sample loops as numba kernels (interpolators, one-pole cascades, first-order section, control-rate interpolation, the visibility follower) with reference implementations; the optimal-2× pre-emphasis design. |
| `source.py` | The processing chain of one source or voice (ADR [0009](adr/0009-processing-chain.md)): emission chain → delay line → per-ear read and stages → gains and pan; held branches crossfaded at jumps; beds. |
| `reverb.py` | EFX presets (`data/efx_presets.json`, from OpenAL Soft) synthesized into stereo impulse responses (seeded, cached), or IR files; `SendLaw`: the send's distance law (EFX room rolloff, revised theory, spreading); `ReverbBus`: overlap-add convolution of the summed send per chunk; decay-time measurement for tests. |
| `mix.py` | Loudness normalization, true peak (BS.1770 interpolator), offline true-peak limiter returning a gain curve, stem file names, WAV writing (float or PCM24 with dither). |
| `report.py` | Peak, true peak, loudness and loudness range for the master and each group, per-source statistics (including visibility), warnings. |
| `plot.py` | Debug plot: distance, level, pan, delay, playback rate and visibility per source over frames (matplotlib, optional). |
| `cull.py` | Culling in the render: the level estimate and upper bound per source and decision block from the baked positions (also used to rank sources for the far field), the skip before setup, the per-voice energy per decision block after setup, and the plan of which voice renders in which chunk. |
| `farfield.py` | The far field (FR-56, ADR 0013): tiers per source and chunk (the `detail_voices` loudest of each group near), dry buffers shared per sample file, per-chunk geometry from the baked positions for many voices at once, per-group buses by distance band and occlusion with their filters, the reverb send per distance band, the crossfade law between tiers. |
| `render.py` | Orchestrates a render: control grid, scene geometry, reverb environment, culling, tiers, renderers per source (near sources: per run of near chunks, on a part of the grid), the far field, chunked rendering in a thread pool, summed in source and group order into group buses (deterministic), reverb bus per chunk, statistics. |

### `soundstage/cli.py`

Argument parsing for `scan`, `bake`, `inspect`, `render`, `presets`, `preview`
([spec/cli.md](spec/cli.md)); `scan` and `bake` shell out to Blender. `render` checks its arguments
against the scene, applies normalization and the limiter, writes the master, stems, report and
plot.

### `soundstage/preview.py`

Muxes a mix with the shot's frame sequence or a video into an MP4 through ffmpeg, aligned by frame
number (gap-free symlinked sequence, whole-sample audio offset). No DSP; runs in the venv.

## Data flow inside a render

1. **Load**: manifest and arrays, resolved settings; samples decoded and resampled to the emission
   rate (2× the output rate for the standard interpolator).
2. **Culling, before setup** (`cull_db`): an upper bound per source and 0.4 s block from the
   baked positions; sources far below the budget everywhere are left out from here on.
3. **Geometry pass** (per source, control rate 1 kHz, whole render range): retarded delay,
   distance, direction, emitter angle, jumps (`Path`); from it the read delays per ear, gains, pan
   gains and filter parameters as control-rate arrays. This also yields report statistics
   (distance, delay and rate ranges). Culling then estimates each voice's energy per block from
   the gains and the dry signal's level and plans which voice renders in which chunk.
4. **Audio pass**, in chunks of 4 s of output: per source, the delay line is extended by the
   emission chain (dry timeline → pre-emphasis → air absorption → rear cue) as far as the reads need,
   then read per ear at fractional positions, filtered per ear (occlusion, head shadow), multiplied
   by gains and pan gains; at jumps a held branch is crossfaded out. A centre read gives the mono
   reverb send. Sources run in parallel threads; their chunks are summed in source order into the
   group buses and the master, their sends into one signal that the reverb bus convolves (tail
   carried to the next chunk). With a reverb, chunks of one impulse-response length before the
   first output sample run first and feed only the reverb bus (pre-roll). All filter states carry
   across chunks; a voice culled for a chunk fades out and in inside the skipped chunk and restarts
   its delay line and filters with a 50 ms warm-up.
5. **Mix**: master gain, trim to the shot; optional normalization and true-peak limiting with the
   same gains on master and stems; write the WAVs.
6. **Report**: metrics for master and groups, per-source statistics, culling summary, warnings;
   optional plot.

Chunking keeps memory bounded (a 5-minute stereo float64 bus is ~230 MB; 50 sources at once would
not fit comfortably) and makes partial renders (`--frames`) cheap. The delay line keeps every
emission sample a later read may still need (a cut to a farther camera reads further back).

## Performance model

Per source and output sample: the emission chain at the 2× rate (63-tap pre-emphasis, two
state-variable sections for air absorption, the rear shelf), one 6-point read per ear, one first-order section
per ear, gains. Geometry at 1 kHz is negligible. Sources render in parallel (numba kernels release
the GIL). Measured with `tools/benchmark.py`: 50 sources × 5 minutes in 42 s on a 16-core desktop
CPU, 63 s with occlusion on every source, a reverb and stems; a single thread 1.6× real time for 50
sources ([E10](../research/experiments/E10-performance.md)).

Bake cost: a sample costs one depsgraph evaluation for the frame plus, every `occlusion_rate`-th
of a second, 25 ray casts per occluding source against the box BVH and a rebuild of the moving
boxes ([E11](../research/experiments/E11-blender-raycast.md)).

Cost per option and against the number of sources: [E15](../research/experiments/E15-option-costs.md).
With culling, render and bake time follow the number of sources that matter at a time rather than
the total ([E16](../research/experiments/E16-culling.md)).

## Testing strategy

- **Reference implementations**: each numba kernel has a slow, obvious numpy version; tests check
  the kernel against it on random input.
- **Known-answer tests** on synthetic scenes built with `write_scene` (no Blender): level per
  distance, constant-power pan, arrival time, Doppler frequency for a given speed, ITD at 90°, loop
  seam continuity, no clicks at cuts or when a source passes through the camera.
- **End-to-end** (`-m blender`): build a small scene from a script, bake headless, render, check
  the onset of a one-shot against its frame and distance, and the pan direction over a flyby.
- **Golden files** are avoided (float noise across library versions); tests assert measured
  quantities with tolerances.

## Integration with a scripted Blender pipeline

- Generator scripts in scene projects import `soundstage.blender.tag` by path (scripts plus data
  rebuild everything, the `.blend` is disposable).
- Bake uses a local headless Blender; no GPU or render farm.
- Scene projects keep audio under `<project>/audio/`: `samples/` (inputs), `bake/<shot>/`,
  `out/` (WAV, report, plot, preview), all binaries outside git.
- Rendered frames come from wherever the pipeline renders them; `soundstage preview` muxes them
  with the mix for a sync check.
