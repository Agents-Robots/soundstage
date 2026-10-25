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
    [--blender PATH]
```

JSON content: `blend_file`, `scene`, `fps`, `frame_start`, `frame_end`, `duration_s`,
`scale_length`, `cameras` (name, first/last sampled frame active), `camera_path` (start, end,
length, max speed), `counts`, `moving` (per object: `name`, `type`, `parent`, `collections`,
`dimensions_m`, `hide_render`, `distance_m` [min, max] to the camera, `closest_frame`,
`side_at_closest` (front/behind, left/right), `path_length_m`, `max_speed_m_s`, `moving_frames`,
`moves_with_camera`, `keyframes`), `static_near` (same fields without motion, nearest first),
`scene_settings`, `tagged` (existing tags). Distances in metres; speeds are estimates from the
sampled frames.

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
    [--scene NAME]           (later) default: the file's active scene
```

Writes `<dir>/scene.json`, `<dir>/scene.npz`. Prints a one-line summary per source. Invalid tags
fail the bake with object, entry index and reason.

## `soundstage inspect`

```
soundstage inspect <scene.json> [--json]
```

Table of sources: id, object, sample, mode, frames, group, distance min/max over the shot,
maximum radial speed, the playback rate it implies. Lists cuts and warnings. Reads only the
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
    [--stems]                (later) also write <mix>_stem_<group>.wav
    [--quality standard|high] (later)
    [--normalize LUFS]       (later) normalize the master to a target loudness
    [--limit DBTP]           (later) true-peak limiter on the master
    [--plot]                 (later) write <mix>.plot.png
```

## `soundstage preview` *(later)*

```
soundstage preview <mix.wav> -o <preview.mp4>
    (--frames PREFIX --fps F | --video FILE)
    [--width W] [--start-frame N]
```

Muxes the audio with a numbered frame sequence (`PREFIX0001.png …`, gaps allowed) or with an existing video, as H.264 + AAC. For checking sync
only; deliverables are the WAVs.

## Report (`<mix>.report.json`)

Example from the flyby example (three of its sources):

```json
{
  "scene": "/\u2026/audio/bake/flyby/scene.json",
  "output": "/\u2026/audio/out/flyby.wav",
  "sample_rate": 48000,
  "frames": [
    1,
    240
  ],
  "fps": 30.0,
  "length_samples": 384000,
  "settings": {
    "\u2026": "effective settings after --set"
  },
  "overrides": {},
  "master": {
    "peak_dbfs": -7.08,
    "true_peak_dbtp": -7.05,
    "lufs_integrated": -23.37
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
      "peak_dbfs": -7.49,
      "audible_frames": 40,
      "distance_m": [
        9.02,
        16.69
      ]
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
      "peak_dbfs": -11.2,
      "audible_frames": 240,
      "distance_m": [
        25.08,
        123.71
      ]
    }
  ],
  "cuts": [],
  "warnings": [],
  "timing_s": {
    "load": 0.014,
    "dsp": 0.125
  }
}
```

Fields: `master` peak (dBFS), true peak (dBTP, 4× oversampled), integrated loudness (LUFS, BS.1770; null for silence or clips shorter than 0.4 s). Per source: `active_frames` [first, last] within the rendered range, `peak_dbfs` of its contribution, `audible_frames` (frames whose peak is above −60 dBFS), `distance_m` [min, max] for spatial sources. *(later)*: per-group metrics, loudness range, playback-rate ranges, per-source warnings.

## Exit criteria for agents

An agent's render step succeeds when the exit code is 0 and the report shows no unexpected
warnings, `true_peak_dbtp` below 0 for PCM output, and every source the shot is meant to feature
having `audible_frames > 0`.
