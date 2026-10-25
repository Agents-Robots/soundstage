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
| `scan.py` | Script run like `bake.py`: samples the shot at evenly spaced frames and writes a JSON list of cameras, moving objects and static objects near the camera, so an agent can choose sound sources. |
| `util.py` | Shared helpers for `bake.py` and `scan.py`: argument handling, running `--run` scripts, frame stepping, output prefix for the CLI. |
| `schema.py` | The tag and settings schema (keys, types, defaults, ranges) as plain data, shared by `tag.py`, `bake.py` and the engine, so defaults exist in one place (NFR-8). Stdlib only. |

### `soundstage/engine/`

| Module | Responsibility |
|---|---|
| `scene.py` | Load `scene.json` + `scene.npz`, check format/version, apply `--set` overrides, build `Scene`/`Source`/`Settings` dataclasses; `write_scene` for tests and hand-made scenes. |
| `signals.py` | Decode and cache samples (soundfile), downmix, resample (soxr) to the emission rate, pitch; `DryGenerator` builds each source's dry timeline window by window over emission time: loop tiling with seam crossfade and seeded phase, one-shot placement, fades. |
| `control.py` | The control grid (1 kHz) and interpolation of control-rate tracks to audio samples (linear for gains and filter parameters, Catmull-Rom for delays), never across a jump. |
| `geometry.py` | Tracks: positions as cubic splines per piece (split at cuts and detected teleports), listener rotation as `RotationSpline` per segment; retarded-time solver (fixed point + Newton, audibility mask); the per-source `Path` on the control grid; camera-space vectors and derived angles. |
| `propagation.py` | Read delays per ear (Doppler factor, picture sync, ITD, playback-rate clamp per run between jumps); interpolator registry (`optimal2x`, `sinc`, `hermite4`); the `DelayLine` of emission samples. |
| `filters.py` | Gain laws (distance models, cone, rear), ISO 9613-1 air absorption and its fitted one-pole cascade, Brown–Duda head-shadow coefficients; stages `OnePoleStage`, `RearStage` (emission side) and `ShelfStage` (per ear). |
| `panning.py` | Pan-law registry (`sine`, `power`) and panner registry (`amplitude`, `hybrid`): per-ear delays (ITD), per-ear stages and pan gains from the path; later `binaural`. |
| `kernels.py` | All per-sample loops as numba kernels (interpolators, one-pole cascade, first-order section) with reference implementations; the optimal-2× pre-emphasis design. |
| `source.py` | The processing chain of one source or voice (ADR [0009](adr/0009-processing-chain.md)): emission chain → delay line → per-ear read and stages → gains and pan; held branches crossfaded at jumps; beds. |
| `reverb.py` | Send bus, IR presets synthesized by seed or loaded from file, partitioned FFT convolution. *(Phase 3)* |
| `mix.py` | WAV writing (float or PCM24 with dither); later group buses and stems, limiter and loudness normalization. |
| `report.py` | Loudness and peak metrics, per-source statistics, warnings; later the debug plot. |
| `render.py` | Orchestrates a render: control grid, scene geometry, renderers per source, chunked rendering with sources in a thread pool, summed in source order (deterministic), statistics. |

### `soundstage/cli.py`

Argument parsing for `scan`, `bake`, `inspect`, `render`, `preview` ([spec/cli.md](spec/cli.md)); `scan` and `bake`
shell out to Blender.

### `soundstage/preview.py`

Muxes a mix with the shot's frame sequence or a video into an MP4 through ffmpeg, aligned by frame
number (gap-free symlinked sequence, whole-sample audio offset). No DSP; runs in the venv.

## Data flow inside a render

1. **Load**: manifest and arrays, resolved settings; samples decoded and resampled to the emission
   rate (2× the output rate for the standard interpolator).
2. **Geometry pass** (per source, control rate 1 kHz, whole render range): retarded delay,
   distance, direction, emitter angle, jumps (`Path`); from it the read delays per ear, gains, pan
   gains and filter parameters as control-rate arrays. This also yields report statistics
   (distance, delay and rate ranges).
3. **Audio pass**, in chunks of 4 s of output: per source, the delay line is extended by the
   emission chain (dry timeline → pre-emphasis → air absorption → rear cue) as far as the reads need,
   then read per ear at fractional positions, filtered per ear (head shadow), multiplied by gains
   and pan gains; at jumps a held branch is crossfaded out. Sources run in parallel threads; their
   chunks are summed in source order. All filter states carry across chunks.
4. **Mix**: master gain, trim to the shot, write the WAV (later: groups, stems, reverb return,
   limiter/normalization).
5. **Report**: metrics, warnings.

Chunking keeps memory bounded (a 5-minute stereo float64 bus is ~230 MB; 50 sources at once would
not fit comfortably) and makes partial renders (`--frames`) cheap. The delay line keeps every
emission sample a later read may still need (a cut to a farther camera reads further back).

## Performance model

Per source and output sample: the emission chain at the 2× rate (63-tap pre-emphasis, four
one-poles for air absorption, the rear shelf), one 6-point read per ear, one first-order section
per ear, gains. Geometry at 1 kHz is negligible. Sources render in parallel (numba kernels release
the GIL). Measured with `tools/benchmark.py`: 50 sources × 5 minutes in 46 s on a 16-core desktop
CPU, a single thread 2.2× real time for 50 sources ([E10](../research/experiments/E10-performance.md)).

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
