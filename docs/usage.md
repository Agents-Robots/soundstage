# Usage

How to give a Blender animation its sound, for people and for coding agents. Everything here works
as described; the Phase 4 tag keys (`variants`, `gain_jitter_db`, `pitch_jitter`, `gain_prop`,
`pitch_prop`) are accepted and stored but ignored with a warning ([roadmap.md](roadmap.md)). For
adding sound to an existing animation step by step, see the [agent guide](agent-guide.md).

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
- Any sample rate and bit depth; everything is resampled to the output rate (48 kHz).
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

Tags can also be added or edited by hand in the UI (Object Properties → Custom Properties). A tag
on an object inside an asset collection gives one source per instance of that collection
(collection instances and geometry-nodes scatters), at most `instance_limit` (32) per tagged object,
the ones that come closest to the camera.

## 2b. Or place Speaker objects by hand

Without scripts, use Blender's own Speaker objects; the bake reads every unmuted speaker in the view
layer:

1. Add → Speaker, place it (parent it to the moving object). Its −Z axis is its front.
2. Object Data → Sound: open a sound file (mono for spatial sound). Blender adds an NLA sound strip
   at the current frame; the speaker plays the whole file once at each strip's start. Duplicate or
   move strips in the NLA editor for more triggers.
3. Volume, Pitch, Distance (reference, maximum, attenuation) and Cone (inner/outer angle, outer
   volume) carry over; the distance model comes from Scene → Audio. Mute a speaker to leave it out.
4. For what a speaker cannot say, add a custom property `sfx_speaker` to the speaker object with a
   dict of tag keys, e.g. `{"mode": "loop", "group": "engines", "reverb_send_db": -6}` (a loop starts
   at the first strip).

Speakers and tags can be mixed in one scene; `tag.set_scene_settings(read_speakers=False)` (in the
scene or in a `--run` script) makes the bake ignore the speakers. The mapping in detail:
[spec/tagging.md](spec/tagging.md#speaker-objects).

## 2c. Environment: occluders and reverb

**Occlusion** works without setup: every rendered mesh larger than 2 m blocks sound with its
bounding box (a merged mesh with the boxes of its parts); a source behind it gets quieter and
duller, smoothly, with the low frequencies bending around edges. Fog and light volumes, light beams
and holograms (light-only materials), text objects and the vehicle the camera rides on are left out
automatically; glass blocks, as it does in reality. Adjust with a custom property `sfx_occluder` on
an object or on the collection that is instanced:

| Object | `sfx_occluder` |
|---|---|
| foliage, fences, nets, grilles, scaffolding, helper meshes that render | `False` |
| arches, gates, L-shaped or hollow buildings (one part with an opening) | `"mesh"` (its real triangles) |

Per source: `occlusion=False` to switch it off, `occlusion_mode="occlusion"` for a source in another
room (behind a closed door: its reverb is muffled too). Scene: `occlusion_gain_db`,
`occlusion_cutoff_hz` set how much passes through walls (render-time, no new bake).

**Reverb**: one environment per shot, by name, at render time or in the scene settings:

```bash
.venv/bin/soundstage presets                    # 113 EFX environments with decay times
.venv/bin/soundstage presets space              # spacestation_hall, spacestation_alcove, ...
.venv/bin/soundstage render …/scene.json -o out/shot.wav --set reverb=hangar
.venv/bin/soundstage render …/scene.json -o out/shot.wav --set reverb=/path/to/hall_ir.wav
```

| Shot | Preset ideas |
|---|---|
| City street, canyon of buildings | `city`, `alley`, `city_streets`, `city_subway` |
| Open landscape | `plain`, `mountains`, `forest`, `outdoors_valley` |
| Hangar, factory, warehouse | `hangar`, `factory_hall`, `factory_largeroom` |
| Space station, ship interior | `spacestation_hall`, `spacestation_largeroom`, `spacestation_cupboard` |
| Tunnel, pipe, sewer | `sewerpipe`, `pipe_large`, `pipe_longthin` |
| Underwater | `underwater` |

All spatial sources send to it (0 dB by default); `reverb_send_db` per source or scene changes the
amount. The reverberant level stays constant with distance while the direct sound falls, which is
what makes far sources sound far.

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
reads as a huge speed), missing cuts, and visibility below 1 for sources that are always in the
open (an occluder to mark `sfx_occluder = False`).

## 4. Render

```bash
.venv/bin/soundstage render <project>/audio/bake/shot1/scene.json \
    -o <project>/audio/out/shot1_mix.wav --stems --report --plot --set reverb=city
```

`--stems` writes one WAV per group (`shot1_mix_stem_engines.wav`, …) and `shot1_mix_stem_reverb.wav`;
they sum to the master. `--plot` draws distance, level, pan, delay, playback rate and visibility per
source over the frames. For a standalone file (not mixed further in Resolve):
`--normalize -23 --limit -1` (EBU R128) or `--normalize -14 --limit -1` (streaming).

Iterate quickly on one part:

```bash
# only frames 200-260, only the engines, with stronger Doppler
.venv/bin/soundstage render …/scene.json -o out/test.wav --frames 200-260 \
    --solo group:engines --set doppler_factor=2
```

## 5. Check sync, then go to Resolve

A quick preview without Resolve (needs ffmpeg; first frame and fps come from the mix's
`.report.json`, so render with `--report`):

```bash
.venv/bin/soundstage preview <project>/audio/out/shot1_mix.wav --frames <project>/renders/shot1/
# -> <project>/audio/out/shot1_mix_preview.mp4
```

The frame numbers in the file names place each image; missing frames hold the previous one, so a
partly rendered shot can be checked already. See [spec/cli.md](spec/cli.md#soundstage-preview).

In DaVinci Resolve:

1. Import the image sequence and `shot1_mix.wav` (and stems if wanted) into the media pool.
2. Put the WAV on an audio track starting **at the same timeline position as the first frame** of
   the shot. The WAV is exactly as long as the shot.
3. The timeline frame rate must equal the Blender frame rate (`fps / fps_base`), and the project
   audio rate should be 48 kHz.
4. Stems go on separate tracks for balancing in Fairlight; their sum equals the master, so use
   either the master or the stems, not both.
5. 32-bit float files can exceed 0 dBFS without clipping; set final levels and limiting in
   Fairlight, or render with `--normalize -23 --limit -1` (the same gains go to the stems).

## For agents

Agents drive the same commands; the step-by-step procedure is the [agent guide](agent-guide.md).
Things that differ from a person's workflow:

- **You cannot listen.** Verify with the report, measurements and the plot (see
  [AGENTS.md](../AGENTS.md#you-cannot-listen-verify-with-numbers-and-pictures)). After each
  render, read `<mix>.report.json` and check: exit code 0; no unexpected warnings; every source
  that the shot is meant to feature has `audible_frames > 0`; `distance_m` and `rate` ranges are
  plausible for the motion; `visibility` and `occluded_frames` match what the picture shows
  (a source behind a building should be occluded there, a source in the open should not); peaks are
  sane. Open `<mix>.plot.png` as an image to check that pan moves to the expected side, Doppler
  peaks where a source passes the camera, and visibility drops where the source is hidden.
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
| Sudden pitch jump or warble | Bad keyframes, a jump slower than `teleport_speed` (not recognized as a teleport), or sub-frames too coarse for very fast motion | `inspect` for speed spikes; lower `teleport_speed`; raise `--substeps` |
| "playback rate clamped" warning | Source near or above Mach 1 | Lower `doppler` for that source, or accept the clamp |
| "a bake setting, it has no effect on a render" warning | `--set` on a setting the bake uses (`substeps`, `pad_seconds`, `occlusion_rate`, `listener`, …) | Set it in the scene settings or a `--run` script and bake again |
| Clicks at a camera cut | Cut not detected: the camera jumps without a camera switch, slower than `teleport_speed` | The engine treats a listener jump faster than `teleport_speed` as a cut: lower `teleport_speed`, or switch cameras with markers |
| Source muffled though it is in view | An open or invisible object blocks it (foliage, a fence, a helper mesh that renders), or a connected part whose box covers open space | `soundstage inspect` lists the objects that block each source; mark them `sfx_occluder=False` (or `"mesh"`) |
| Muffled through an arch or open structure | Its bounding box closes the opening | `sfx_occluder="mesh"` on that object |
| Too many or too few engines in instanced traffic | `instance_limit` keeps the 32 closest per tagged object | Raise or lower `instance_limit` in the scene settings |
| Bake slow with occlusion | Many occluding sources or moving occluders | `tag.set_scene_settings(occlusion_rate=5)`; `occlusion=False` on distant sources that are never hidden |
