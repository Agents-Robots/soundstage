# Spec: command-line interface and outputs

One entry point, `soundstage`, with subcommands. Exit code 0 on success, 1 on errors (bad input,
missing files), 2 on usage errors. Warnings go to stderr and into the report; they never change
the exit code unless `--strict` is given.

## `soundstage bake`

Runs Blender headless on a .blend and writes the scene file.

```
soundstage bake <file.blend> --out <dir>
    [--frames A-B]           default: scene frame range
    [--scene NAME]           default: the file's active scene
    [--substeps N]           default: scene setting (4)
    [--pad SECONDS]          default: scene setting (3.0)
    [--run SCRIPT.py ...]    run generator scripts first (scene built from scratch, NFR-1)
    [--skip-invalid]         drop invalid tags with a warning instead of failing
    [--blender PATH]         default: `blender` on PATH
```

Equivalent to
`blender -b <file.blend> --factory-startup -y --python soundstage/blender/bake.py -- --out <dir> ...`,
which also works directly (the wrapper only builds this command line and checks the result).

Writes `<dir>/scene.json`, `<dir>/scene.npz`. Prints a one-line summary per source.

## `soundstage inspect`

```
soundstage inspect <scene.json> [--json]
```

Table of sources: id, object, sample, mode, frames, group, distance min/max over the shot,
maximum radial speed, the playback rate it implies. Lists cuts and warnings. Reads only the
scene file and sample headers; renders nothing. `--json` for machine use.

## `soundstage render`

```
soundstage render <scene.json> -o <mix.wav>
    [--frames A-B]           sub-range (output sample 0 = frame A)
    [--stems]                also write <mix>_stem_<group>.wav
    [--solo ID|GROUP ...]    render only these (globs allowed: "Ship.*", "group:engines")
    [--mute ID|GROUP ...]
    [--set KEY=VALUE ...]    override scene settings, e.g. --set doppler_factor=2 --set panner=amplitude
    [--quality standard|high]
    [--pcm24]                24-bit PCM with TPDF dither instead of 32-bit float
    [--normalize LUFS]       normalize the master to a target loudness
    [--limit DBTP]           true-peak limiter on the master
    [--report]               write <mix>.report.json (always written when --plot is given)
    [--plot]                 write <mix>.plot.png
    [--strict]               warnings become errors
```

## `soundstage preview`

```
soundstage preview <mix.wav> -o <preview.mp4>
    (--frames PREFIX --fps F | --video FILE)
    [--width W] [--start-frame N]
```

Muxes the audio with a numbered frame sequence (`PREFIX0001.png …`, gaps allowed) or with an existing video, as H.264 + AAC. For checking sync
only; deliverables are the WAVs.

## Report (`<mix>.report.json`)

```json
{
  "scene": "/…/audio/bake/shot1/scene.json",
  "output": "/…/audio/out/shot1_mix.wav",
  "sample_rate": 48000, "frames": [1, 600], "fps": 30.0, "length_samples": 960000,
  "settings": {"…": "effective settings after --set"},
  "master": {"peak_dbfs": -4.1, "true_peak_dbtp": -3.8, "lufs_integrated": -21.7, "lra_lu": 6.2},
  "groups": {"engines": {"peak_dbfs": -6.0, "lufs_integrated": -24.0}},
  "sources": [
    {"id": "Ship.001:0", "group": "engines", "active_frames": [[1, 600]],
     "distance_m": [4.2, 812.0], "rate": [0.93, 1.08], "peak_dbfs": -7.5,
     "audible_frames": 540, "warnings": []}
  ],
  "cuts": [301.0],
  "warnings": ["Ship.003:0: playback rate clamped at 4.0 in frames 410-414"],
  "timing_s": {"load": 0.8, "geometry": 0.3, "dsp": 12.1, "write": 0.4}
}
```

## Exit criteria for agents

An agent's render step succeeds when the exit code is 0 and the report shows no unexpected
warnings, `true_peak_dbtp` below 0 for PCM output, and every source the shot is meant to feature
having `audible_frames > 0`.
