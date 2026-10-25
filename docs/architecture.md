# Architecture

How `soundstage` is built and why. Exact formats and formulas are in [spec/](spec/); the
decisions behind the structure are in [adr/](adr/README.md).

## Pipeline

```
┌──────────────────────────── Blender (bpy, headless) ────────────────────────────┐
│ generator scripts ──▶ tag.add_sound(obj, …) ──▶ obj["sfx"], scene["sfx_settings"] │
│                                                    │                              │
│ bake.py: validate tags, step frames + sub-frames, record listener and sources,   │
│          ray-cast visibility, detect cuts ──▶ scene.json + scene.npz             │
└──────────────────────────────────────────────────────┬──────────────────────────┘
                                                       │ files (versioned contract)
┌──────────────────────────── engine (venv: numpy, scipy, numba) ──────────────────┐
│ scene.py      load + validate + resolve settings (--set)                          │
│ signals.py    samples → dry timelines (resample, pitch, loops, one-shots, fades)  │
│ geometry.py   splines per segment, control-rate listener/source geometry          │
│ propagation.py retarded time, Doppler/sync/ITD delays, fractional-delay read       │
│ filters.py    distance gain, cone, air absorption, rear cue, occlusion, head shadow│
│ panning.py    amplitude / hybrid (binaural later)                                  │
│ reverb.py     send bus, synthetic or file IR, partitioned convolution (Phase 3)   │
│ mix.py        group buses, master, limiter/normalize, WAV writing                  │
│ report.py     metrics, warnings, plot                                              │
│ render.py     orchestrates per source and per chunk                                │
└──────────────────────────────────────────────────────┬──────────────────────────┘
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
| `bake.py` | Script run with `blender -b … --python bake.py -- <args>`. Resolves the listener per frame, steps through frames and sub-frames (`scene.frame_set(f, subframe=s)`), reads evaluated world matrices from the depsgraph, applies tag offsets, ray-casts visibility (Phase 3), detects cuts, resolves sample paths and defaults, writes the scene file. Uses Blender's bundled numpy. |
| `schema.py` | The tag and settings schema (keys, types, defaults, ranges) as plain data, shared by `tag.py`, `bake.py` and the engine, so defaults exist in one place (NFR-8). Stdlib only. |

### `soundstage/engine/`

| Module | Responsibility |
|---|---|
| `scene.py` | Load `scene.json` + `scene.npz`, check format/version, apply `--set` overrides, build `Scene`/`Source`/`Settings` dataclasses; `write_scene` for tests and hand-made scenes. |
| `signals.py` | Decode and cache samples (soundfile), downmix, resample (soxr), pitch; build each source's dry timeline over emission time: loop tiling with seam crossfade and seeded phase, one-shot placement, fades. |
| `geometry.py` | Segment the timeline at cuts; cubic splines for positions, quaternion slerp for listener rotation; evaluate listener pose and source positions at control rate; camera-space vectors and derived angles. |
| `propagation.py` | Retarded-time solver, Doppler factor and picture sync, ITD offsets, playback-rate clamp, upsampling of delays to audio rate, fractional-delay read kernels (cubic, windowed sinc). |
| `filters.py` | Gain laws (distance models, cone, rear, occlusion), cutoff laws (air absorption, rear, occlusion), time-varying one-pole low-pass and head-shadow shelf kernels. |
| `panning.py` | Pan gains for `amplitude` and `hybrid`; later `binaural` (HRIR selection and interpolation). |
| `reverb.py` | Send bus, IR presets synthesized by seed or loaded from file, partitioned FFT convolution. *(Phase 3)* |
| `mix.py` | Group buses, master gain, optional limiter and loudness normalization, WAV and stem writing, dither for PCM. |
| `report.py` | Loudness and peak metrics, per-source statistics, warnings, the debug plot. |
| `render.py` | Orchestrates a render: plan chunks, process each source per chunk through propagation → filters → panning, accumulate buses, hand over to mix and report. |

### `soundstage/cli.py`

Argument parsing for `bake`, `inspect`, `render`, `preview` ([spec/cli.md](spec/cli.md)); `bake`
shells out to Blender, `preview` to ffmpeg.

## Data flow inside a render

1. **Load**: manifest and arrays, resolved settings. Fail early on missing samples.
2. **Geometry pass** (all sources, control rate 1 kHz, cheap): retarded time, delays, all gains
   and cutoffs as control-rate arrays per source. This also yields report statistics (distance
   range, rate range) and allows **culling**: sources whose gain stays below −80 dB for a whole
   chunk are skipped there.
3. **Audio pass**, in chunks of ~10 s with overlap for filter state and delay reach: per source,
   fractional-delay read of the dry timeline (two ears), then the filter cascade, gains, pan,
   accumulate into its group bus and the reverb send. Filter states carry across chunks.
4. **Mix**: groups → master (+ reverb return), optional limiter/normalization, trim to the shot,
   write files.
5. **Report**: metrics, warnings, plot.

Chunking keeps memory bounded (a 5-minute stereo float64 bus is ~230 MB; 50 sources at once would
not fit comfortably) and makes partial renders (`--frames`) cheap.

## Performance model

Per source and audio sample: one fractional-delay read per ear (4 taps standard, 32 high), three
one-pole/shelf sections per ear, two gains. At 48 kHz, 50 sources, 300 s that is ~1.4·10⁹
source-samples; numba kernels at ~10⁸–10⁹ simple ops/s per core give a few minutes on one core,
less with sources processed in parallel (threads in numba, `prange` over sources). Geometry at
1 kHz is about 2 % of that. NFR-3 (≤ real time for 50 sources) is the target from Phase 2.

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
