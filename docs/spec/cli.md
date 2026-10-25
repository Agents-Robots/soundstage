# Spec: command-line interface and outputs

One entry point, `soundstage`, with subcommands. Options marked *(later)* are specified but not
implemented yet; the phase is in [roadmap.md](../roadmap.md). Exit code 0 on success, 1 on errors (bad input,
missing files), 2 on usage errors. Warnings go to stderr and into the report; they never change
the exit code unless `--strict` is given.

Blender is found as `--blender PATH`, else `$SOUNDSTAGE_BLENDER`, else `blender` on `PATH`. The
`scan` and `bake` wrappers run
`blender -b <file.blend> --factory-startup -y --python-exit-code 1 --python soundstage/blender/<script>.py -- ...`,
print the script's own output lines (prefixed `[soundstage]` by the script) and, on failure, the
tail of Blender's output. The scripts also work when run that way directly.

`--run SCRIPT.py` (repeatable) runs a script inside Blender before scanning or baking, in the same
session; nothing is saved to the .blend. This is how tags are applied to an existing animation
without modifying it, and how scenes built from scripts are rebuilt (NFR-1).

## `soundstage scan`

Lists what in a shot could make sound.

```
soundstage scan <file.blend>
    [--out scan.json]        keep the full JSON (otherwise only the tables are printed)
    [--frames A-B]           default: scene frame range
    [--samples N]            frames sampled evenly over the shot (default 60)
    [--max-static N]         static objects in the JSON (default 30)
    [--limit N]              rows per printed table (default 25)
    [--run SCRIPT.py ...]
    [--scene NAME]           default: the file's active scene
    [--blender PATH]
```

JSON content: `blend_file`, `scene`, `fps`, `frame_start`, `frame_end`, `duration_s`,
`scale_length`, `cameras` (name, first/last sampled frame active), `camera_path` (start, end,
length, max speed), `counts`, `moving` (per object: `name`, `type`, `parent`, `collections`,
`dimensions_m`, `hide_render`, `distance_m` [min, max] to the camera, `closest_frame`,
`side_at_closest` (front/behind, left/right), `path_length_m`, `max_speed_m_s`, `moving_frames`,
`moves_with_camera`, `keyframes`), `static_near` (same fields without motion, nearest first),
`scene_settings`, `tagged` (existing tags), `speakers` (Speaker objects: `name`, `sound`, `packed`,
`strip_frames`, `muted`, `volume`, `overrides` from `sfx_speaker`), `instanced_tags` (tagged objects
reached through instances, with the number of instances). Distances in metres; speeds are estimates
from the sampled frames.

## `soundstage bake`

Runs Blender headless on a .blend and writes the scene file.

```
soundstage bake <file.blend> --out <dir>
    [--frames A-B]           default: scene frame range
    [--substeps N]           default: scene setting (4)
    [--pad SECONDS]          default: scene setting (3.0)
    [--run SCRIPT.py ...]    tagging or generator scripts to run first
    [--skip-invalid]         drop invalid tags with a warning instead of failing
    [--blender PATH]
    [--scene NAME]           default: the file's active scene
```

Writes `<dir>/scene.json`, `<dir>/scene.npz`. Prints a one-line summary per source. Invalid tags
fail the bake with object, entry index and reason.

`--scene` (bake and scan) makes the named scene the context scene before the `--run` scripts run,
so scripts that use `bpy.context.scene` see it too; the manifest records it as `scene`.

## `soundstage inspect`

```
soundstage inspect <scene.json> [--json]
```

Table of sources: id, group, sample, mode, frames, distance min/max over the shot, maximum radial
speed, the playback-rate range it implies (estimated from the baked samples; the render
report has the exact values), and the baked visibility range (mean of the bands; 1 = in the open).
Below the table, for each occluded source, the objects that block it most (share of its paths over
the shot): the objects to look at when a source is muffled although it should not be. Lists cuts and warnings. Reads only the
scene file and sample headers; renders nothing. `--json` for machine use.

## `soundstage render`

```
soundstage render <scene.json>
    [-o <mix.wav>]           default: mix.wav next to scene.json
    [--frames A-B]           sub-range (output sample 0 = frame A)
    [--solo ID|GROUP ...]    render only these (globs allowed: "Ship:*", "group:engines")
    [--mute ID|GROUP ...]
    [--set KEY=VALUE ...]    override scene settings, e.g. --set master_gain_db=-6
    [--pcm24]                24-bit PCM with TPDF dither instead of 32-bit float
    [--report]               write <mix>.report.json
    [--strict]               warnings become errors (exit 1)
    [--stems]                also write <mix>_stem_<group>.wav per group, and <mix>_stem_reverb.wav
    [--quality standard|high] fractional-delay interpolation (same as --set quality=...)
    [--normalize LUFS]       normalize the master to a target loudness (e.g. -23, -14)
    [--limit DBTP]           true-peak limiter on the master (e.g. -1)
    [--plot]                 write <mix>.plot.png (needs matplotlib: pip install 'soundstage[plot]')
```

Stems sum to the master; `--normalize` and `--limit` apply the same gains to the master and every
stem, in that order (normalize, then limit). Typical calls:

```
soundstage render shot/scene.json -o out/shot.wav --report --plot                  # check
soundstage render shot/scene.json -o out/shot.wav --stems --set reverb=city        # for Fairlight
soundstage render shot/scene.json -o out/shot.wav --normalize -23 --limit -1       # standalone mix
```

The plot (`<mix>.plot.png`) shows, for up to the 12 loudest spatial sources on a frame axis:
distance, level (gain × distance × cone, dB), pan, delay, playback rate and, with occlusion,
visibility. Read it as an image to check a render without listening.

## `soundstage presets`

```
soundstage presets [TEXT]    list the reverb presets whose names contain TEXT (default: all 113)
```

Table of the EFX environments: name, decay time at mid frequencies, low and high decay times (s),
and the preset's early-plus-late level (dB). Use a name as `--set reverb=<name>` or scene setting
`reverb`.

## `soundstage preview`

```
soundstage preview <mix.wav>
    (--frames DIR|PREFIX | --video FILE)
    [-o <preview.mp4>]       default: <mix>_preview.mp4 next to the WAV
    [--fps F]                default: from <mix>.report.json
    [--start-frame N]        frame of the mix's first sample; default: from <mix>.report.json
    [--video-start-frame N]  frame of the video's first frame; default: --start-frame
    [--width W]              output width, 0 keeps the size (default 1280)
    [--ffmpeg PATH]          default: $SOUNDSTAGE_FFMPEG, else ffmpeg on PATH
```

Muxes the mix with the shot's picture into an H.264 + AAC MP4, for checking sync without Resolve;
the deliverables are the WAVs.

- `--frames DIR` takes the largest set of numbered images in the directory that share a prefix and
  extension (`000001.png`, `frame_0001.exr`); `--frames DIR/frame_` takes only `frame_<n>.<ext>`.
  The number in the file name is the Blender frame. Gaps (a partly rendered shot) hold the previous
  image, so the timing stays right. Images are linked into a gap-free sequence in a temporary
  directory and read at the exact rational frame rate (29.97 → 30000/1001).
- `--video FILE` must have the mix's frame rate; with `--width 0` its video stream is copied.
- Picture and sound are aligned by frame number: the MP4 starts at the first picture frame, the
  mix is trimmed (or delayed with silence) by a whole number of samples so that the sound of frame
  N plays with picture frame N, and padded with silence if the picture runs longer. The MP4 is as
  long as the picture (AAC rounds the audio up to a whole 1024-sample frame).
- Without a report next to the mix, `--start-frame` and `--fps` are required.
- EXR frames are shown as ffmpeg decodes them (linear, not view-transformed); render PNG or JPG
  previews for a faithful picture.

## Report (`<mix>.report.json`)

Example from the flyby example rendered with `--report --set reverb=city` (three of its sources,
two of its groups):

```json
{
  "scene": "/…/audio/bake/flyby/scene.json",
  "output": "/…/audio/out/flyby.wav",
  "sample_rate": 48000,
  "frames": [
    1,
    240
  ],
  "fps": 30.0,
  "length_samples": 384000,
  "settings": {
    "…": "effective settings after --set"
  },
  "overrides": {
    "reverb": "city"
  },
  "master": {
    "peak_dbfs": -6.05,
    "true_peak_dbtp": -6.05,
    "lufs_integrated": -22.9,
    "loudness_range_lu": 4.11
  },
  "reverb": "city",
  "groups": {
    "engines": {
      "peak_dbfs": -9.01,
      "true_peak_dbtp": -9.0,
      "lufs_integrated": -25.52,
      "loudness_range_lu": 5.46
    },
    "reverb": {
      "peak_dbfs": -24.18,
      "true_peak_dbtp": -24.17,
      "lufs_integrated": -36.78,
      "loudness_range_lu": 0.75
    },
    "…": "one entry per group"
  },
  "sources": [
    {
      "id": "Ambience:0",
      "group": "ambience",
      "sample": "ambience_stereo.wav",
      "mode": "loop",
      "spatial": false,
      "active_frames": [
        1,
        240
      ],
      "peak_dbfs": -18.0,
      "audible_frames": 240
    },
    {
      "id": "Crate:0",
      "group": "sfx",
      "sample": "impact.wav",
      "mode": "once",
      "spatial": true,
      "active_frames": [
        180.0,
        225.0
      ],
      "peak_dbfs": -7.77,
      "audible_frames": 41,
      "distance_m": [
        9.02,
        16.69
      ],
      "delay_ms": [
        26.3,
        48.7
      ],
      "rate": [
        0.9995,
        1.0113
      ],
      "visibility": [
        1.0,
        1.0
      ],
      "occluded_frames": 0
    },
    {
      "id": "Ship:0",
      "group": "engines",
      "sample": "engine_hum.wav",
      "mode": "loop",
      "spatial": true,
      "active_frames": [
        1,
        240
      ],
      "peak_dbfs": -11.14,
      "audible_frames": 240,
      "distance_m": [
        24.99,
        123.71
      ],
      "delay_ms": [
        72.9,
        360.7
      ],
      "rate": [
        0.9204,
        1.0942
      ],
      "visibility": [
        1.0,
        1.0
      ],
      "occluded_frames": 0
    }
  ],
  "cuts": [],
  "warnings": [],
  "timing_s": {
    "load": 1.175,
    "dsp": 0.199,
    "workers": 5
  },
  "processing": {}
}
```

Fields:

- `master` and each entry of `groups` (one per group, and `reverb` for the reverb return): sample
  peak (dBFS), true peak (dBTP, 4× oversampled, BS.1770-4), integrated loudness (LUFS, BS.1770;
  null for silence or clips shorter than 0.4 s), loudness range (LU, EBU Tech 3342; null for clips
  shorter than 3 s).
- `reverb`: the environment (preset name or file), null without reverb.
- `processing`: `normalize_gain_db`, `limiter_max_reduction_db`, `limiter_active_s` when
  `--normalize` / `--limit` were given.
- Per source: `active_frames` [first, last] within the rendered range, `peak_dbfs` of its
  contribution, `audible_frames` (frames whose peak is above −60 dBFS); spatial sources also
  `distance_m` [min, max] (propagation distance), `delay_ms` [min, max] (propagation delay as read,
  after the Doppler factor), `rate` [min, max] (playback rate: above 1 approaching, below 1
  receding); with baked visibility `visibility` [min, max] (per frame, mean of the bands) and
  `occluded_frames` (frames with visibility below 0.5).
- Warnings: unimplemented keys, sources never audible, playback rate clamped (near- or supersonic
  motion), sound emitted before the baked range (padding too short).

## Exit criteria for agents

An agent's render step succeeds when the exit code is 0 and the report shows no unexpected
warnings, `true_peak_dbtp` below 0 for PCM output, and every source the shot is meant to feature
having `audible_frames > 0`.
