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
| `frame` | float \| [float] \| null | null | Once: trigger frame, or a list of trigger frames (required). Loop: start frame; null = running since before the shot. Fractional frames allowed. |
| `end_frame` | float \| null | null | Loop only: stop at this frame (after `fade_out`); null = runs to the end. |
| `fade_in` | float s | 0.0 (once), 0.05 (loop with `frame`) | Fade-in duration. |
| `fade_out` | float s | 0.05 | Fade-out duration at `end_frame` (loop). |
| `loop_phase` | float s \| `"random"` | `"random"` | Loop start offset into the sample at `frame` (or at the shot start); `"random"` is seeded from `id`. |
| `loop_crossfade` | float s | 0.05 | Crossfade at the loop seam (correlation-adaptive, constant level); 0 for samples that are already seamless. |
| `gain_db` | float | 0.0 | Source gain at the reference distance. |
| `pitch` | float | 1.0 | Playback-rate ratio applied before spatial processing (2.0 = one octave up, shorter). |
| `group` | str | `"sfx"` | Stem name. |
| `spatial` | bool | true | false = bed: no distance, pan, delay, filters; only gain and fades. |
| `distance_model` | str | `"inverse_clamped"` | `inverse_clamped`, `linear_clamped`, `exponential_clamped`, `none` ([formulas](signal-model.md#distance-gain)). |
| `ref_distance` | float m | 1.0 | Distance at which the gain is `gain_db`. Closer does not get louder. |
| `max_distance` | float m \| null | null | Beyond this the gain stops falling (inverse/exponential) or reaches 0 (linear, required there). Also the culling distance. |
| `rolloff` | float | 1.0 | Steepness of the distance model. |
| `offset` | [x, y, z] m | [0, 0, 0] | Emitter position in object-local coordinates. |
| `forward_axis` | str | `"-Z"` | Object axis the cone points along: `±X`, `±Y`, `±Z`. Same default as Blender Speaker objects. |
| `cone_inner_deg` | float | 360 | Full angle of the cone with full gain. |
| `cone_outer_deg` | float | 360 | Full angle beyond which the gain is `cone_outer_gain_db`. |
| `cone_outer_gain_db` | float | −12.0 | Gain outside the outer cone. |
| `doppler` | float | 1.0 | Multiplies the scene's `doppler_factor` for this source. |
| `air_absorption` | float | 1.0 | Multiplies the scene's `air_absorption`. |
| `sync_to_picture` | bool | false | One-shots: remove the propagation delay at the trigger, so the onset lands on `frame`. Doppler during playback stays. |
| `occlusion` | bool | true | Apply occlusion from the baked visibility. *(Phase 3)* |
| `occlusion_radius` | float m | 0.5 | Spread of the visibility rays around the emitter (soft occlusion edges). *(Phase 3)* |
| `reverb_send_db` | float \| null | null | Send level to the scene reverb; null = scene default. *(Phase 3)* |
| `variants` | [str] | [] | Alternative samples; one is picked per trigger, seeded. *(Phase 4)* |
| `gain_jitter_db`, `pitch_jitter` | float | 0.0 | Random variation per trigger, seeded. *(Phase 4)* |
| `gain_prop`, `pitch_prop` | str \| null | null | Name of an animated custom property on the object that modulates gain (dB, added) or pitch (ratio, multiplied). *(Phase 4)* |

Repeated one-shots (e.g. footsteps, a beacon every 2 s) are one entry with a list of frames:
`add_sound(obj, "beep.wav", mode="once", frame=[100, 160, 220])`. Overlapping triggers add up.

## Scene settings: `scene["sfx_settings"]`

A dict on the scene. Missing keys take the default. Command-line `--set key=value` overrides it.

| Key | Default | Meaning |
|---|---|---|
| `samples_root` | `"//audio/samples/"` | Base for relative sample paths. |
| `sample_rate` | 48000 | Output sample rate. |
| `speed_of_sound` | 343.0 m/s | Propagation speed. |
| `doppler_factor` | 1.0 | 0 = no Doppler (constant delay), 1 = physical, >1 exaggerated. |
| `air_absorption` | 1.0 | Scales the air absorption coefficient (ISO 9613-1); 0 = off. |
| `air_temperature_c` | 20.0 | Air temperature for the absorption coefficient. |
| `air_humidity_pct` | 50.0 | Relative humidity for the absorption coefficient. |
| `teleport_speed` | null | Speed (m/s) between two baked samples above which a source or the listener counts as teleported (no Doppler glide across the jump); null = 3 × `speed_of_sound`. |
| `panner` | `"hybrid"` | `amplitude`, `hybrid`; `binaural` in Phase 4. |
| `pan_law` | `"sine"` | `sine` (φ = (λ+1)π/4) or `power` (g² = (1 ± λ)/2, softer at the sides, as Blender's speakers). |
| `itd_scale` | 0.5 | Fraction of the physical interaural time difference used by `hybrid`. |
| `head_shadow` | 0.5 | Strength of the head-shadow filter in `hybrid` (0 = off, 1 = full spherical-head model). |
| `head_radius` | 0.0875 m | Listener head radius. |
| `rear_cutoff_hz` | 6000 | Low-pass cutoff for a source directly behind the camera. |
| `rear_gain_db` | −2.0 | Extra gain for a source directly behind the camera. |
| `master_gain_db` | 0.0 | Gain on the master sum. |
| `substeps` | 4 | Bake sub-frames per frame. |
| `pad_seconds` | 3.0 | Bake padding before and after the shot (covers ~1 km of propagation; the bake warns if a source is farther away in travel time). |
| `listener` | null | Object name to use instead of the active camera. |
| `quality` | `"standard"` | Fractional-delay interpolation: `standard` (2× oversampled, 6-point polynomial) or `high` (anti-aliased windowed sinc, slower; for extreme Doppler). |
| `occlusion_gain_db` | −12.0 | Gain of a fully occluded source. *(Phase 3)* |
| `occlusion_cutoff_hz` | 1500 | Low-pass cutoff of a fully occluded source. *(Phase 3)* |
| `reverb` | null | Preset name or impulse-response path. *(Phase 3)* |
| `reverb_send_db` | −18.0 | Default reverb send. *(Phase 3)* |

Ranges and the full signal meaning: [signal-model.md](signal-model.md).

## Helper API (`soundstage/blender/tag.py`)

```python
add_sound(obj, sample, *, mode="loop", frame=None, **params) -> dict
    # Validate params against the table above, append the entry to obj["sfx"], return it.
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

Storage: lists of dicts are stored as ID property group arrays; checked in Blender 5.2 including
save and reload, `None` values and booleans. A JSON string in `obj["sfx"]` is accepted as well.
