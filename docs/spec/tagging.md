# Spec: tagging sources in Blender

How a scene declares its sounds. Generator scripts call `soundstage.blender.tag`; the result is
plain data in custom properties, so it is saved in the .blend, visible in the UI (Object
Properties → Custom Properties) and editable by any script. Decision: ADR
[0003](../adr/0003-tags-as-custom-properties.md).

## Object tag: `obj["sfx"]`

A list of dicts, one per sound, stored as an ID property on the **object** (not the mesh data, so
linked duplicates can carry different sounds). Keys not listed below are an error at bake time
(catches typos). Missing keys take the default.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `sample` | str | required | Path to the sample. `//` prefix = relative to the .blend; a bare relative path resolves against the scene's `samples_root`. |
| `id` | str | `"<object name>:<index>"` | Stable source id: used in reports, solo/mute, and as random seed. Set it explicitly when object names are not stable. |
| `mode` | `"loop"` \| `"once"` | `"loop"` | Loop the sample, or play it once. |
| `frame` | float \| null | null | Once: trigger frame (required). Loop: start frame; null = running since before the shot. Fractional frames allowed. |
| `end_frame` | float \| null | null | Loop only: stop at this frame (after `fade_out`); null = runs to the end. |
| `fade_in` | float s | 0.0 (once), 0.05 (loop with `frame`) | Fade-in duration. |
| `fade_out` | float s | 0.05 | Fade-out duration at `end_frame` (loop). |
| `loop_phase` | float s \| `"random"` | `"random"` | Loop start offset into the sample at `frame` (or at the shot start); `"random"` is seeded from `id`. |
| `loop_crossfade` | float s | 0.05 | Equal-power crossfade at the loop seam; 0 for samples that are already seamless. |
| `gain_db` | float | 0.0 | Source gain at the reference distance. |
| `pitch` | float | 1.0 | Playback-rate ratio applied before spatial processing (2.0 = one octave up, shorter). |
| `group` | str | `"sfx"` | Stem name. |
| `spatial` | bool | true | false = bed: no distance, pan, delay, filters; only gain and fades. |
| `distance_model` | str | `"inverse_clamped"` | `inverse_clamped`, `linear_clamped`, `exponential_clamped`, `none` ([formulas](signal-model.md#distance-gain)). |
| `ref_distance` | float m | 1.0 | Distance at which the gain is `gain_db`. Closer does not get louder. |
| `max_distance` | float m \| null | null | Beyond this the gain stops falling (inverse/exponential) or reaches 0 (linear, required there). Also the culling distance. |
| `rolloff` | float | 1.0 | Steepness of the distance model. |
| `offset` | [x, y, z] m | [0, 0, 0] | Emitter position in object-local coordinates. *(Phase 2)* |
| `forward_axis` | str | `"-Z"` | Object axis the cone points along: `±X`, `±Y`, `±Z`. Same default as Blender Speaker objects. *(Phase 2)* |
| `cone_inner_deg` | float | 360 | Full angle of the cone with full gain. *(Phase 2)* |
| `cone_outer_deg` | float | 360 | Full angle beyond which the gain is `cone_outer_gain_db`. *(Phase 2)* |
| `cone_outer_gain_db` | float | −12.0 | Gain outside the outer cone. *(Phase 2)* |
| `doppler` | float | 1.0 | Multiplies the scene's `doppler_factor` for this source. *(Phase 2)* |
| `air_absorption` | float | 1.0 | Multiplies the scene's `air_absorption`. *(Phase 2)* |
| `sync_to_picture` | bool | false | One-shots: remove the propagation delay at the trigger, so the onset lands on `frame`. Doppler during playback stays. *(Phase 2)* |
| `occlusion` | bool | true | Apply occlusion from the baked visibility. *(Phase 3)* |
| `occlusion_radius` | float m | 0.5 | Spread of the visibility rays around the emitter (soft occlusion edges). *(Phase 3)* |
| `reverb_send_db` | float \| null | null | Send level to the scene reverb; null = scene default. *(Phase 3)* |
| `variants` | [str] | [] | Alternative samples; one is picked per trigger, seeded. *(Phase 4)* |
| `gain_jitter_db`, `pitch_jitter` | float | 0.0 | Random variation per trigger, seeded. *(Phase 4)* |
| `gain_prop`, `pitch_prop` | str \| null | null | Name of an animated custom property on the object that modulates gain (dB, added) or pitch (ratio, multiplied). *(Phase 4)* |

Repeated one-shots (e.g. footsteps, a beacon every 2 s) are several entries with different
`frame`s; the helper `add_sound(..., frame=[100, 160, 220])` expands a list into entries.

## Scene settings: `scene["sfx_settings"]`

A dict on the scene. Missing keys take the default. Command-line `--set key=value` overrides it.

| Key | Default | Meaning |
|---|---|---|
| `samples_root` | `"//audio/samples/"` | Base for relative sample paths. |
| `sample_rate` | 48000 | Output sample rate. |
| `speed_of_sound` | 343.0 m/s | Propagation speed. |
| `doppler_factor` | 1.0 | 0 = no Doppler (constant delay), 1 = physical, >1 exaggerated. |
| `air_absorption` | 1.0 | Scales the air absorption coefficient; 0 = off. |
| `panner` | `"hybrid"` | `amplitude`, `hybrid`; `binaural` in Phase 4. |
| `itd_scale` | 0.5 | Fraction of the physical interaural time difference used by `hybrid`. |
| `head_shadow` | 0.5 | Strength of the head-shadow filter in `hybrid` (0 = off, 1 = full spherical-head model). |
| `head_radius` | 0.0875 m | Listener head radius. |
| `rear_cutoff_hz` | 6000 | Low-pass cutoff for a source directly behind the camera. |
| `rear_gain_db` | −2.0 | Extra gain for a source directly behind the camera. |
| `master_gain_db` | 0.0 | Gain on the master sum. |
| `substeps` | 4 | Bake sub-frames per frame. |
| `pad_seconds` | 3.0 | Bake padding before and after the shot (covers ~1 km of propagation). |
| `listener` | null | Object name to use instead of the active camera. |
| `quality` | `"standard"` | Fractional-delay interpolation: `standard` (cubic) or `high` (windowed sinc). *(Phase 2)* |
| `occlusion_gain_db` | −12.0 | Gain of a fully occluded source. *(Phase 3)* |
| `occlusion_cutoff_hz` | 1500 | Low-pass cutoff of a fully occluded source. *(Phase 3)* |
| `reverb` | null | Preset name or impulse-response path. *(Phase 3)* |
| `reverb_send_db` | −18.0 | Default reverb send. *(Phase 3)* |

Ranges and the full signal meaning: [signal-model.md](signal-model.md).

## Helper API (`soundstage/blender/tag.py`)

```python
add_sound(obj, sample, *, mode="loop", frame=None, **params) -> list[dict]
    # Validate params against the table above, append entries to obj["sfx"], return them.
clear_sounds(obj) -> None
set_scene_settings(scene=None, **settings) -> dict
    # Merge into scene["sfx_settings"] (default: bpy.context.scene).
iter_tagged(scene=None) -> Iterator[tuple[Object, dict]]
    # All (object, entry) pairs of the scene's view layer; used by bake.
```

The helper imports only `bpy` and the standard library. Generator scripts add the repo to
`sys.path` and import it:

```python
import sys
sys.path.insert(0, "/path/to/soundstage")
from soundstage.blender import tag

tag.set_scene_settings(doppler_factor=1.5, samples_root="//audio/samples/")
tag.add_sound(ship, "engine_hum.wav", gain_db=-6, ref_distance=20, group="engines",
              offset=(0, -12, 0))
tag.add_sound(ship, "flyby_whoosh.wav", mode="once", frame=212, ref_distance=30)
tag.add_sound(scene_root, "station_ambience.wav", spatial=False, gain_db=-20, group="ambience")
```

## Validation at bake time

- Unknown key, wrong type, value out of range → error naming object, entry index and key.
- `mode="once"` without `frame` → error.
- `distance_model="linear_clamped"` without `max_distance` → error.
- Sample file missing or unreadable → error (bake checks existence; the engine decodes).
- `--skip-invalid` turns errors into warnings and drops the entry.

Open point to verify in Phase 1: lists of dicts are stored as ID property arrays of groups in
Blender 5.x. If that turns out fragile, the fallback is a JSON string in `obj["sfx"]`; the bake
accepts both.
