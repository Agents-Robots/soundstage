# Agent guide: add sound to an existing animation

Step-by-step instructions for a coding agent that is asked to give an existing Blender animation
its sound with soundstage. Follow the steps in order. Everything runs headless; the .blend file is
never modified.

What you produce:

- `<project>/audio/sounds.py`: a tagging script (which object makes which sound, when);
- `<project>/audio/bake/<shot>/scene.json` + `scene.npz`: the baked scene;
- `<project>/audio/out/<shot>.wav` + `<shot>.report.json` + `<shot>.plot.png`: the stereo mix, its
  report and its debug plot; stems `<shot>_stem_<group>.wav` if the user mixes in Fairlight;
- `<project>/audio/out/<shot>_preview.mp4`: the mix on the rendered frames, if there are any.

What the engine does (Phases 0 to 3): loudness by distance; sound travels at 343 m/s, so distant events
are heard late; Doppler from the motion of sources and camera; left/right panning with a small
interaural delay and head shadow; air absorption (distant sounds lose treble); a mild treble cut and
level drop for sources behind the camera; directivity cones; clean camera cuts; occlusion behind
buildings and vehicles (quieter and duller, low frequencies bending around edges); a reverb
environment by preset name; loops, one-shots and ambience beds; Speaker objects and tags inside
instanced assets as sources; stems per group, loudness report, optional normalization and limiter;
a 48 kHz float WAV that starts exactly at the first frame; an MP4 preview on the rendered frames.
Not yet: binaural or ambisonic output, animated parameters ([roadmap](roadmap.md)).

## 0. Setup (once per checkout)

```bash
cd /path/to/soundstage
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python tools/make_test_samples.py     # placeholder sounds in samples/
```

Blender 5.x must be on `PATH` (or set `SOUNDSTAGE_BLENDER`). Below, `soundstage` means
`/path/to/soundstage/.venv/bin/soundstage`.

## 1. Collect the facts

You need: the path of the .blend, the shot (frame range; default is the scene's range), and the
sounds. Ask the user for the sound samples they want to use and where they are. If they have
none yet, use the placeholders in `samples/` (`engine_hum.wav`, `whoosh.wav`, `impact.wav`,
`beep.wav`, `ambience_stereo.wav`) and say so; real samples can be swapped in later without
changing anything else.

## 2. Scan the shot

```bash
soundstage scan <project>/shot.blend --out <project>/audio/scan.json
```

Read the printed tables and the JSON:

- `cameras`, `camera_path`: which camera renders the shot and how it moves. If the camera does not
  move and nothing moves except for a few frames, the file may be a still image (motion-blur
  keyframes), not an animation; check with the user.
- `moving`: objects that move, sorted by their closest distance to the camera, with
  `distance_m` (min-max), `closest_frame`, `side_at_closest`, `max_speed_m_s`, `moving_frames`,
  `keyframes` and `collections`. These are the candidates for engine loops, flybys and impacts.
  `moves_with_camera: true` means it is attached to the camera (a cockpit, a held object, or
  just the camera rig); these come last and are left out of the printed table.
- `static_near`: static objects closest to the camera path: machines, doors, beacons, waterfalls.
- `speakers`: Speaker objects already in the scene. The bake reads them as sources (unless muted),
  so do not tag the same sound again; tell the user which speakers you found. `tagged` and
  `instanced_tags`: sounds that are already there (an asset tagged once, placed in many instances,
  gives one source per instance, the 32 closest by default).
- If the scene is built by generator scripts, also read them: names and comments tell you what
  objects are.

If the shot needs scripts to be run first (e.g. a scene built from scratch), pass them with
`--run` here and in the bake.

## 3. Decide the sound list

Write down, for each sound: object, sample, loop or one-shot, frames, gain, reference distance.
Rules of thumb:

| Source | Mode | `ref_distance` | Notes |
|---|---|---|---|
| Vehicle, ship, machine | loop | about its size: 5-50 m | `group="engines"` |
| Flyby accent | once, `frame` = closest frame − the pass moment in the sample | as the engine | whoosh without baked pitch fall: the engine adds the Doppler |
| Impact, door, explosion | once, `frame` = the frame of the event | 2-20 m | from `keyframes` or `moving_frames` (end of a fall); `sync_to_picture=True` if it must hit on the frame |
| Repeating event (beacon, footsteps) | once, `frame=[...]` | 0.5-3 m | one source, list of frames |
| Ambience, room tone, music | loop, `spatial=False` | — | on any object, `group="ambience"` |

- The inverse distance law loses 6 dB per doubling beyond `ref_distance`. A source whose
  `distance_m` minimum is 20× its `ref_distance` peaks at −26 dB: raise `ref_distance` or `gain_db`
  if it must be heard.
- Sound is heard `distance / 343` s after it is emitted: one frame (30 fps) per 11 m. An explosion
  300 m away is heard 26 frames late, which sells scale but can look like a sync error on a cut; set
  `sync_to_picture=True` on one-shots that must land on their frame (the Doppler during the sound
  stays).
- A sound that should point somewhere (a horn, a jet nozzle, a loudspeaker): `forward_axis` and
  `cone_inner_deg` / `cone_outer_deg` / `cone_outer_gain_db`.
- Doppler too strong or too weak for the story: scene `doppler_factor` (0 = off, 1 = physical), or
  per source `doppler`.
- Keep the number of sources small (up to ~50); prefer the few objects that the viewer looks at.
  For traffic or crowds that come from instanced assets, tag the asset object once and let
  `instance_limit` pick the nearest instances.
- Frames are in the scene's frame numbers; fractional frames are allowed.

Then decide the **environment**:

- **Reverb**: pick one preset for the shot with `soundstage presets` (`city` or `city_streets` for
  streets, `hangar`, `forest`, `mountains`, `spacestation_hall`, `sewerpipe` …) and set it in the
  tagging script (`tag.set_scene_settings(reverb="city")`) or at render time (`--set reverb=city`).
  If unsure, render two candidates and compare the reports (`groups.reverb.lufs_integrated`) and ask
  the user. The send falls with distance by default (`reverb_send_law=revised`), so thousands of
  distant sources do not fill the reverb; a shot that sounds too dry overall takes a higher
  `reverb_send_db`, and `reverb_send_law=efx` keeps the reverberant level constant at any distance
  (right for a few sources in one closed room).
- **Occluders**: rendered meshes block sound by their bounding boxes (merged meshes by the boxes of
  their parts) automatically; light-only materials (fog, haze, light beams, holograms) and the camera's own
  vehicle are left out, glass blocks. Look for objects whose boxes are wrong and mark them in the
  tagging script: open objects (trees, fences, nets, scaffolding, helper meshes that render)
  `obj["sfx_occluder"] = False`; parts with openings `obj["sfx_occluder"] = "mesh"`.
  Instanced assets: set it on the collection (`bpy.data.collections["Trees"]["sfx_occluder"] = False`).
- A source in another room (behind a closed door): `occlusion_mode="occlusion"`.

## 4. Write the tagging script

Copy [examples/sounds_template.py](../examples/sounds_template.py) to `<project>/audio/sounds.py`,
set `SOUNDSTAGE` to the repo path and `SAMPLES` to the sample folder, and fill the `SOUNDS` table.
[examples/flyby_sounds.py](../examples/flyby_sounds.py) is a complete example. All parameters:
[spec/tagging.md](spec/tagging.md). Invalid parameters fail the bake with the object name and the
reason.

## 5. Bake

```bash
soundstage bake <project>/shot.blend --run <project>/audio/sounds.py --out <project>/audio/bake/<shot>
soundstage inspect <project>/audio/bake/<shot>/scene.json
```

The bake prints one line per source, the number of occluders (static and moving boxes) and the
time the visibility took; `inspect` shows each source's distance range, the playback-rate range
its motion implies (Doppler), its visibility range and, below the table, the objects that block
each occluded source most. If a source that should be heard is blocked by something that does not
block sound (a railing, trees, a helper mesh, a part whose box closes an opening), mark that object
in the tagging script (`sfx_occluder = False` or `"mesh"`) and bake again. Keep the defaults (`--substeps 4 --pad 3`) when
you can: sub-frames keep fast motion smooth, and the padding must cover the travel time of sound that is
heard from the first frame on but was emitted before it (the bake warns otherwise, with the `--pad`
it needs; sources that start with a later shot need none). The bake costs one scene
evaluation per sub-frame; for very heavy scenes `--substeps 2` is fine for objects slower than
about 50 m/s, but never drop the padding below what the warning asks for. Visibility adds ray casts
per occluding source every 0.1 s; with many sources and moving occluders, lower it with
`tag.set_scene_settings(occlusion_rate=5)` or switch it off per source (`occlusion=False`) for
sources that are never hidden (beds are never occluded).

## 6. Render

```bash
soundstage render <project>/audio/bake/<shot>/scene.json -o <project>/audio/out/<shot>.wav --report --plot
```

Add `--stems` when the user mixes in Fairlight (one file per group plus the reverb return; they sum
to the master). Do not normalize or limit unless the user asks for a finished file
(`--normalize -23 --limit -1`).

To check one source or group in isolation: `--solo 'Ship:*'`, `--solo group:engines`; to drop one:
`--mute 'Beacon:0'`; a part of the shot: `--frames 100-180`.

Culling is on by default (`cull_db` −40): per group, sources that add less than −40 dB to the group
are skipped where they do not matter. `--set cull_db=-20` for a quicker preview; `--set
cull_db=null` for a reference render. Beyond 64 sources in a group (`detail_voices`), the quieter
ones render in the far field, so shots with thousands of sources (traffic, crowds) render in minutes:
tag every car, not a selection ([usage](usage.md#4-render)).

## 7. Verify (you cannot listen)

Read `<shot>.report.json` and check:

- exit code 0, and no `warnings` you cannot explain;
- every source has `audible_frames > 0`; a source that should be prominent has a `peak_dbfs`
  between about −30 and −3. A source with `culled_s` equal to the shot length was skipped by
  culling: it is more than 40 dB below its group; if it matters, give it its own group or raise
  its gain;
- `master.peak_dbfs` below 0 and `lufs_integrated` roughly −30 to −16 for an effects mix;
- `distance_m` ranges match what the scan said; `delay_ms` ≈ `distance_m` / 0.343 (2.9 ms per metre);
- `rate` (playback rate) of moving sources: above 1 while approaching, below 1 while receding,
  `c / (c ∓ v)` for speed `v` (30 m/s ≈ 1.10 / 0.92); a warning "playback rate clamped" means
  near-supersonic motion (lower `doppler` for that source) or a jump the engine did not recognize
  as a teleport (check `scene["sfx_settings"]["teleport_speed"]`);
- `visibility` [min, max] and `occluded_frames` per source: a source in the open should stay at 1;
  one that passes behind a building should drop where the picture hides it. A source muffled while
  in view points to an occluder to mark `sfx_occluder = False` or `"mesh"`: `soundstage inspect`
  lists the objects that block each source;
- `groups`: loudness per group; `groups.reverb` 10–20 LU below the master is a usual amount of
  space; with `--stems`, the stems exist for every group.

Open `<shot>.plot.png` as an image: per source, distance, level, pan (−1 left, +1 right), delay,
playback rate and visibility over the frames. Pan should move to the side the object passes on, the
rate should cross 1 at the closest approach, and visibility should drop where the source is hidden.

For a stronger check, render single sources with `--solo` and measure with numpy/soundfile: the
onset of a one-shot is at sample `round((frame − frame_start) · 48000 / fps)` plus its travel time
(exactly on the frame with `sync_to_picture`); a source left of the camera is louder in channel 0,
right in channel 1. A spectrogram of a solo render (`scipy.signal.spectrogram`, saved as PNG) shows
the Doppler glide of a passing source; read it as an image.

## 8. Preview and hand over

If the shot has rendered frames (any numbered PNG/JPG sequence, even a partial one), make a preview
so the user can check sync without Resolve:

```bash
soundstage preview <project>/audio/out/<shot>.wav --frames <frames dir>
```

It reads the first frame and fps from `<shot>.report.json`, places each image by the frame number
in its file name and holds the previous image over missing frames (it prints how many). Ask the
user where the frames are if you cannot find them; never render frames yourself for this.

Tell the user where the WAV (and the preview) is, what each source is, and what you measured. Ask them to listen:
put the WAV on the Resolve timeline at the first frame of the shot (timeline frame rate = the
scene's fps). Adjust `gain_db`, `ref_distance` or the samples from their feedback and re-run
steps 5-7.
