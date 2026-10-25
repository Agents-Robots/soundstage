# Usage

How to give a Blender animation its sound, for people and for coding agents. Features marked
*(later)* are specified but not implemented yet; [roadmap.md](roadmap.md) says which phase delivers
them. For adding sound to an existing animation step by step, see the
[agent guide](agent-guide.md).

## Setup (once)

```bash
cd /path/to/soundstage
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'              # numpy, scipy, soundfile, soxr, numba, pyloudnorm, pytest
.venv/bin/python tools/make_test_samples.py    # test sounds into samples/
.venv/bin/pytest                               # unit tests
```

Blender needs nothing installed: generator scripts import the tag helper by path, and the bake
script runs with `--python`.

## Project layout for audio

In a scene project (`<project>/`):

```
<project>/
├── scripts/                 generator scripts (tags are added here)
├── audio/
│   ├── samples/             input sounds (WAV/FLAC/OGG; not in git, note their source and licence in README)
│   ├── bake/<shot>/         scene.json + scene.npz (rebuilt by bake)
│   └── out/                 <shot>_mix.wav, stems, report, plot, preview (rebuilt by render)
└── renders/<shot>/          rendered frames
```

## 1. Choose and prepare samples

- **Loops** (engines, hums, machinery, ambience): seamless if possible; otherwise the engine
  crossfades the seam (`loop_crossfade`). A few seconds long at least, so the repetition is not
  obvious.
- **One-shots** (impacts, doors, flybys, beeps): trimmed to the onset (no leading silence), or
  the visual sync is off by that silence.
- **Mono** for anything placed in space (stereo files are downmixed). Stereo for beds
  (ambience, music) with `spatial=False`.
- Any sample rate and bit depth; everything is resampled to 48 kHz.
- Level: normalize samples to a similar peak (e.g. −1 dBFS) and set the balance with `gain_db`
  in the tags, so the mix is controlled in one place.

## 2. Tag objects

Tags are added by a script that runs inside Blender. Two ways to use it:

- **Existing animation**: a separate tagging script next to the project, applied at bake time with
  `soundstage bake <blend> --run <project>/audio/sounds.py`. The .blend stays untouched. Start
  from [examples/sounds_template.py](../examples/sounds_template.py); find object names with
  `soundstage scan <blend>`.
- **Scene built by generator scripts**: call the tag helper in the generator script itself, so the
  tags are saved with the scene.

Either way the calls are the same:

```python
import sys
sys.path.insert(0, "/path/to/soundstage")
from soundstage.blender import tag

tag.set_scene_settings(samples_root="//audio/samples/", doppler_factor=1.0)

# A ship with an engine hum at its rear nozzle, audible from far away
tag.add_sound(ship, "engine_hum.wav", gain_db=-6, ref_distance=20, rolloff=1.0,
              offset=(0, -12, 0), group="engines")

# A flyby whoosh that should hit exactly when the ship passes the camera
tag.add_sound(ship, "whoosh.wav", mode="once", frame=212, ref_distance=30, sync_to_picture=True)

# A blinking beacon every 2 s (60 frames at 30 fps)
tag.add_sound(beacon, "beep.wav", mode="once", frame=list(range(1, 601, 60)), ref_distance=5)

# A door that opens and closes, heard only from the front
tag.add_sound(door, "door_motor.wav", mode="loop", frame=300, end_frame=360, fade_out=0.2,
              forward_axis="-Y", cone_inner_deg=120, cone_outer_deg=240, cone_outer_gain_db=-15)

# Station ambience, not placed in space
tag.add_sound(bpy.context.scene.objects["World_Root"], "station_room_tone.wav",
              spatial=False, gain_db=-24, group="ambience")
```

Rules of thumb for parameters:

| Situation | Setting |
|---|---|
| Large, loud source (ship engine, waterfall) | `ref_distance` 10–50 m, rolloff 1 |
| Small source (beep, console, footsteps) | `ref_distance` 0.5–2 m, rolloff 1 |
| Should stay present across the whole shot | lower `rolloff` (0.5) or set `max_distance` |
| Should vanish completely beyond some range | `distance_model="linear_clamped"`, `max_distance` |
| One-shot must hit on the frame regardless of distance | `sync_to_picture=True` |
| Doppler too subtle / too strong for the story | scene `doppler_factor` 1.5–3 / 0.3–0.5 |
| Space scene that should feel "quieter" | scene `air_absorption` 2–4, lower `reverb_send_db` |

Tags can also be added or edited by hand in the UI (Object Properties → Custom Properties), or by
placing Blender Speaker objects (from Phase 3).

## 3. Bake

```bash
.venv/bin/soundstage bake <project>/shot.blend --out <project>/audio/bake/shot1
# or rebuild from scripts first (NFR-1):
.venv/bin/soundstage bake <project>/shot.blend --run <project>/scripts/build.py --out <project>/audio/bake/shot1
```

Bake again whenever the animation, the camera or the tags change. Then check it:

```bash
.venv/bin/soundstage inspect <project>/audio/bake/shot1/scene.json
```

Look for sources that never get close enough to be heard, implausible speeds (a source teleporting
reads as a huge speed), and missing cuts.

## 4. Render

```bash
.venv/bin/soundstage render <project>/audio/bake/shot1/scene.json \
    -o <project>/audio/out/shot1_mix.wav --stems --report --plot
```

Iterate quickly on one part:

```bash
# only frames 200-260, only the engines, with stronger Doppler
.venv/bin/soundstage render …/scene.json -o out/test.wav --frames 200-260 \
    --solo group:engines --set doppler_factor=2
```

## 5. Check sync, then go to Resolve

*(later)* a quick preview without Resolve:

```bash
.venv/bin/soundstage preview <project>/audio/out/shot1_mix.wav \
    --frames <project>/renders/shot1/frame_ --fps 30 -o <project>/audio/out/shot1_preview.mp4
```

In DaVinci Resolve:

1. Import the image sequence and `shot1_mix.wav` (and stems if wanted) into the media pool.
2. Put the WAV on an audio track starting **at the same timeline position as the first frame** of
   the shot. The WAV is exactly as long as the shot.
3. The timeline frame rate must equal the Blender frame rate (`fps / fps_base`), and the project
   audio rate should be 48 kHz.
4. Stems go on separate tracks for balancing in Fairlight; their sum equals the master, so use
   either the master or the stems, not both.
5. 32-bit float files can exceed 0 dBFS without clipping; set final levels and limiting in
   Fairlight (*(later)*: render with `--normalize -23 --limit -1`).

## For agents

Agents drive the same commands; the step-by-step procedure is the [agent guide](agent-guide.md).
Things that differ from a person's workflow:

- **You cannot listen.** Verify with the report, measurements and (later) the plot (see
  [AGENTS.md](../AGENTS.md#you-cannot-listen-verify-with-numbers-and-pictures)). After each
  render, read `<mix>.report.json` and check: exit code 0; no unexpected warnings; every source
  that the shot is meant to feature has `audible_frames > 0`; `distance_m` and `rate` ranges are
  plausible for the motion; peaks are sane. Open `<mix>.plot.png` as an image to check that pan
  moves to the expected side and Doppler peaks where a source passes the camera.
- **Tag in generator scripts, never only in a live session.** A tag set in a live Blender session but not
  in `scripts/` is lost when the scene is rebuilt (NFR-1).
- **Bake reads the file on disk**: `soundstage bake` runs `blender -b … --factory-startup -y`. If
  another Blender session holds the same .blend with unsaved changes, save it first.
- **Sync check without ears**: for a one-shot with a visible event, the onset in the WAV should be
  at `t(frame) + d / c` (or `t(frame)` with `sync_to_picture`); measure the onset (first sample
  above −40 dB relative to the event peak) and compare.
- **Ask the user to listen** at the end of each phase or when a sound design choice is subjective
  (which sample, how strong the Doppler, how much reverb). Report what was measured and what
  needs their ears.
- **Record lessons**: tuning results go into [spec/signal-model.md](spec/signal-model.md) (replace
  *(tune)* values with the tuned ones and why).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Event sound late compared to picture | Propagation delay (by design) or leading silence in the sample | `sync_to_picture=True`; trim the sample |
| Audio drifts against picture over the shot | Resolve timeline fps differs from Blender fps | Match timeline fps to `fps/fps_base` |
| Source inaudible | `ref_distance` too small for the scene scale, or wrong `scale_length` | Check `distance_m` in the report; raise `ref_distance` |
| Sudden pitch jump or warble | Object teleports or bad keyframes; sub-frames too coarse for very fast motion | `inspect` for speed spikes; raise `--substeps` |
| "playback rate clamped" warning | Source near or above Mach 1 | Lower `doppler` for that source, or accept the clamp |
| Clicks at a camera cut | Cut not detected (camera jumps without a camera switch) | Bake detects jumps above a threshold; report a bug with the scene file |
