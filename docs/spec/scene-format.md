# Spec: scene file (`scene.json` + `scene.npz`)

The contract between the Blender bake and the engine. A bake writes one directory per shot:

```
<out>/scene.json   manifest: time base, settings, sources with resolved parameters
<out>/scene.npz    arrays: listener and source trajectories, visibility, cuts
<out>/sounds/      sounds packed in the .blend and used by Speaker objects (only if any)
```

Decision: ADR [0004](../adr/0004-scene-interchange-json-npz.md). The format can be written by
anything (tests build scene files in pure Python without Blender).

## Versioning

`format` is `"soundstage.scene"`, `version` is an integer (currently 2). The engine refuses any
other version, except version 1 files, which it still reads (they lack `listener_frame`, so
`pan_reference = "screen"`, the default, falls back to the camera with a warning). Version 2 added
`listener_frame`. Adding optional keys or arrays does not bump the version; renaming, removing or
changing the meaning of a key does, together with this spec.

## `scene.json`

```json
{
  "format": "soundstage.scene",
  "version": 2,
  "created": "2026-10-25T14:03:11Z",
  "generator": {"tool": "soundstage.blender.bake", "blender_version": "5.2.2"},
  "blend_file": "/projects/demo/shot.blend",
  "scene": "Scene",

  "time": {
    "fps": 30,
    "fps_base": 1.0,
    "frame_start": 1,
    "frame_end": 600,
    "substeps": 4,
    "pad_frames_before": 90,
    "pad_frames_after": 90
  },
  "units": {"scale_length": 1.0},

  "settings": {
    "samples_root": "//audio/samples/",
    "sample_rate": 48000,
    "speed_of_sound": 343.0,
    "doppler_factor": 1.0,
    "air_absorption": 1.0,
    "air_temperature_c": 20.0,
    "air_humidity_pct": 50.0,
    "teleport_speed": null,
    "panner": "hybrid",
    "pan_law": "sine",
    "itd_scale": 0.5,
    "head_shadow": 0.5,
    "head_radius": 0.0875,
    "rear_cutoff_hz": 6000.0,
    "rear_gain_db": -2.0,
    "master_gain_db": 0.0,
    "substeps": 4,
    "pad_seconds": 3.0,
    "listener": null,
    "quality": "standard",
    "occlusion_gain_db": -12.0,
    "occlusion_cutoff_hz": 1500.0,
    "reverb": "city",
    "reverb_send_db": 0.0,
    "reverb_room_rolloff": null,
    "read_speakers": true,
    "occlusion_rate": 10.0,
    "occluder_min_size": 2.0,
    "instance_limit": 32,
    "cull_db": -40.0
  },

  "listener": {"objects": ["Camera", "Camera.002"]},

  "sources": [
    {
      "id": "Ship.001:0",
      "object": "Ship.001",
      "index": 0,
      "track": 0,
      "sample": "/projects/demo/audio/samples/engine_hum.wav",
      "mode": "loop",
      "frame": null,
      "end_frame": null,
      "fade_in": 0.0,
      "fade_out": 0.05,
      "loop_phase": "random",
      "loop_crossfade": 0.05,
      "gain_db": -6.0,
      "pitch": 1.0,
      "group": "engines",
      "spatial": true,
      "distance_model": "inverse_clamped",
      "ref_distance": 20.0,
      "max_distance": null,
      "rolloff": 1.0,
      "offset": [0.0, -12.0, 0.0],
      "forward_axis": "-Z",
      "cone_inner_deg": 360.0,
      "cone_outer_deg": 360.0,
      "cone_outer_gain_db": -12.0,
      "doppler": 1.0,
      "air_absorption": 1.0,
      "sync_to_picture": false,
      "occlusion": true,
      "occlusion_radius": 0.25,
      "occlusion_mode": "obstruction",
      "reverb_send_db": null
    }
  ],

  "occlusion": {
    "bands_hz": [250.0, 1000.0, 4000.0],
    "samples": 2010,
    "occluders": {"static": 111180, "moving": 7002, "carried": 9},
    "geometry": "boxes",
    "culled_share": 0.31,
    "blockers": {"Ship.001:0": [["Hangar", 0.42], ["Crane", 0.05]]}
  },

  "arrays": "scene.npz",
  "warnings": []
}
```

Rules:

- `blend_file` and `scene` say where the bake came from (`bake --scene` picks a scene other than
  the file's active one); the engine does not read them.
- `time.fps / time.fps_base` is the frame rate (Blender's own representation; 29.97 is
  `fps=30, fps_base=1.001`).
- Sample paths are **absolute** (resolved by the bake from `//`, `samples_root`); bake and render must
  run where these paths resolve.
- Every source parameter is **resolved**: defaults filled in, so the engine never needs Blender's
  defaults. Scene settings likewise.
- `track` is the source's row in the source arrays (several sources on one object share the
  object's trajectory but have their own track because offsets differ).
- Bed sources (`spatial: false`) have no track (`"track": null`).
- `frame` of a one-shot is a number or a sorted list of numbers (repeated triggers).
- `listener.objects` lists every camera that is active during the shot, in order of first use.
- `object` names where the source comes from: the object name for a tag or a Speaker object,
  `"<instancer>/<object>"` (collection instance) or `"<instancer>/<object>#<n>"` (geometry-nodes or
  nested instance) for a tag inside an instance. Speaker sources have ids `"<object>:speaker"`.
- `occlusion` describes the baked visibility: frequency bands of `src_visibility`, number of
  visibility samples, occluder counts (static and moving boxes, objects left out because they
  travel with the listener), and per source up to three objects that block it most, with the share
  of all its paths over the shot they block (`"<instancer>/<object>"` for instances); `culled_share`:
  the share of (source, sample) visibility values culling skipped (null with `cull_db` null). `null`
  when no source occludes or `occlusion_rate` is 0.

## `scene.npz`

Let `N` = number of time samples = `(frame_end − frame_start + pad_before + pad_after) · substeps + 1`,
`S` = number of tracks.

| Array | Shape, dtype | Meaning |
|---|---|---|
| `frames` | (N,) float64 | Frame number of each time sample (sub-frames fractional), strictly increasing, uniform step `1/substeps`. |
| `listener_matrix` | (N, 4, 4) float64 | Listener world matrix, scale removed (orthonormal rotation, translation in metres). |
| `listener_index` | (N,) int16 | Index into `listener.objects` of the active camera. |
| `listener_frame` | (N, 2) float64 | The frame's left and right edges as `x / −z` in camera space (the tangents of their azimuths), from the evaluated camera's `view_frame`: lens, sensor fit, render aspect and shift included, so a zoom is a change over time. NaN where the listener is not a perspective camera. Used by `pan_reference = "screen"`. Optional (absent in version 1). |
| `cuts` | (C,) float64 | Frames where the active camera switches. A cut lies between two time samples; its value is the first sample after it. (Listener jumps without a camera switch are detected by the engine from the trajectory, faster than `teleport_speed`.) |
| `src_pos` | (N, S, 3) float64 | Emitter world position (object matrix applied to `offset`), metres. |
| `src_fwd` | (N, S, 3) float32 | Unit vector of the emitter's `forward_axis` in world space (absent = omnidirectional). |
| `vis_frames` | (M,) float64 | Frames of the visibility samples (every `round(fps · substeps / occlusion_rate)`-th time sample). |
| `src_visibility` | (M, S, B) float32 | Visibility 0…1 per band (`occlusion.bands_hz`, B = 3): the open share of the first Fresnel zone of the path heard at that frame, from the source's retarded position to the listener ([model](../../research/models/occlusion.md)). Absent: fully visible. Sources with `occlusion: false` have 1. Samples culling skipped (sources far below the budget, [signal-model.md](signal-model.md#culling)) hold the value interpolated from the source's computed samples, 1 where none was computed. |
| `src_cuts` | (K, 2) float64 | `(track, frame)` pairs where a source teleports. Optional: the bake writes it empty, because the engine detects teleports itself from `src_pos` (speed above `teleport_speed`); other tools may fill it. |
| `prop_<name>` | (N, S) float32 | Sampled animated property values (`gain_prop`, `pitch_prop`). *(Phase 4)* |

Conventions:

- Positions are in metres: Blender units × `scale_length`.
- Time of a time sample in seconds relative to the first frame of the shot:
  `t = (frames − frame_start) · fps_base / fps` (negative in the pre-roll padding).
- The listener is the camera's world matrix; its local axes are +X right, +Y up, −Z view
  direction (Blender camera convention). See [signal-model](signal-model.md#coordinate-frames).
- Values outside the baked range are held constant (first/last sample).
- The engine checks on load that `frames` is strictly increasing and covers `frame_start` to
  `frame_end`, and that the other arrays have the shapes above; otherwise it refuses the file.

## Producing scene files without Blender

Tests and hand-written cues build the same structure in Python with
`soundstage.engine.scene.build_manifest(...)` and `write_scene(path, manifest, arrays)`. Example
use: a static listener at the origin, one source moving along a line at a known speed
(`tests/conftest.py`, `research/experiments/scripts/common.py`).
