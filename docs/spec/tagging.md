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
| `end_frame` | float \| null | null | Loop only: the fade-out starts at this frame and ends `fade_out` later; null = runs to the end. |
| `fade_in` | float s | 0.0 (once), 0.05 (loop with `frame`) | Fade-in duration. |
| `fade_out` | float s | 0.05 | Fade-out duration at `end_frame` (loop). |
| `loop_phase` | float s \| `"random"` | `"random"` | Loop start offset into the sample at `frame` (or at the shot start); `"random"` is seeded from `id`. |
| `loop_crossfade` | float s | 0.05 | Crossfade at the loop seam (correlation-adaptive, constant level); 0 for samples that are already seamless. |
| `gain_db` | float | 0.0 | Source gain at the reference distance. |
| `pitch` | float | 1.0 | Playback-rate ratio applied before spatial processing (2.0 = one octave up, shorter). |
| `group` | str | `"sfx"` | Stem name (`reverb` is the reverb return's stem; avoid it). |
| `spatial` | bool | true | false = bed: no distance, pan, delay, filters; only gain and fades. |
| `distance_model` | str | `"inverse_clamped"` | `inverse_clamped`, `linear_clamped`, `exponential_clamped`, `none` ([formulas](signal-model.md#distance-gain)). |
| `ref_distance` | float m | 1.0 | Distance at which the gain is `gain_db`. Closer does not get louder. |
| `max_distance` | float m \| null | null | Beyond this the gain stops falling (inverse/exponential) or reaches 0 (linear, required there). Not smaller than `ref_distance`. |
| `rolloff` | float | 1.0 | Steepness of the distance model. |
| `offset` | [x, y, z] m | [0, 0, 0] | Emitter position in object-local coordinates. |
| `forward_axis` | str | `"-Z"` | Object axis the cone points along: `±X`, `±Y`, `±Z`. Same default as Blender Speaker objects. |
| `cone_inner_deg` | float | 360 | Full angle of the cone with full gain. |
| `cone_outer_deg` | float | 360 | Full angle beyond which the gain is `cone_outer_gain_db`. |
| `cone_outer_gain_db` | float | −12.0 | Gain outside the outer cone. |
| `doppler` | float | 1.0 | Multiplies the scene's `doppler_factor` for this source. |
| `air_absorption` | float | 1.0 | Multiplies the scene's `air_absorption`. |
| `sync_to_picture` | bool | false | One-shots: remove the propagation delay at the trigger, so the onset lands on `frame`. Doppler during playback stays. |
| `occlusion` | bool | true | Bake visibility for this source and apply occlusion ([model](../../research/models/occlusion.md)). |
| `occlusion_radius` | float m | 0.25 | Size of the source: the smallest radius of the visibility points around the path (soft edges for large sources). |
| `occlusion_mode` | `"obstruction"` \| `"occlusion"` | `"obstruction"` | `obstruction`: only the direct sound is occluded, the reverb send stays (a car behind a pillar, same space). `occlusion`: the send is occluded too (behind a closed door, another space). |
| `reverb_send_db` | float \| null | null | Send level to the scene reverb, added to the scene's `reverb_send_db`; null = 0 dB for spatial sources, no send for beds. |
| `variants` | [str] | [] | Alternative samples; one is picked per trigger, seeded. *(Phase 4)* |
| `gain_jitter_db`, `pitch_jitter` | float | 0.0 | Random variation per trigger, seeded. *(Phase 4)* |
| `gain_prop`, `pitch_prop` | str \| null | null | Name of an animated custom property on the object that modulates gain (dB, added) or pitch (ratio, multiplied). *(Phase 4)* |

Repeated one-shots (e.g. footsteps, a beacon every 2 s) are one entry with a list of frames:
`add_sound(obj, "beep.wav", mode="once", frame=[100, 160, 220])`. Overlapping triggers add up.

## Scene settings: `scene["sfx_settings"]`

A dict on the scene. Missing keys take the default. Command-line `--set key=value` overrides it.

| Key | Default | Meaning |
|---|---|---|
| `samples_root` | `"//audio/samples/"` | Base for relative sample paths (bake). |
| `sample_rate` | 48000 | Output sample rate. |
| `speed_of_sound` | 343.0 m/s | Propagation speed. |
| `doppler_factor` | 1.0 | 0 = no Doppler (constant delay), 1 = physical, >1 exaggerated. |
| `air_absorption` | 1.0 | Scales the air absorption coefficient (ISO 9613-1); 0 = off. |
| `air_temperature_c` | 20.0 | Air temperature for the absorption coefficient. |
| `air_humidity_pct` | 50.0 | Relative humidity for the absorption coefficient. |
| `teleport_speed` | null | Speed (m/s) between two baked samples above which a source or the listener counts as teleported (no Doppler glide across the jump); null = 3 × `speed_of_sound`. |
| `panner` | `"hybrid"` | `amplitude`, `hybrid`; `binaural` in Phase 4. |
| `pan_law` | `"sine"` | `sine` (φ = (λ+1)π/4) or `power` (g² = (1 ± λ)/2, softer at the sides, as Blender's speakers). |
| `pan_reference` | `"screen"` | `screen`: sources in the frame are panned to where a viewer sees them on the screen, through the lens (zooms move them); off-screen directions are stretched to the sides; distance, delay, Doppler and occlusion are unchanged ([signal-model.md](signal-model.md#panning)); needs a scene baked with format version 2, otherwise panning follows the camera with a warning. `camera`: direction relative to the camera, independent of the lens (as in games and Blender's speakers). |
| `screen_edge_deg` | 16.5 | With `pan_reference = "screen"`: the angle from the centre at which the viewer sees the left and right screen edges; the frame edge is panned to be heard there on loudspeakers at ±30°. 16.5° is a 16:9 screen at 3 picture heights (HD); about 25 for a large TV or close viewing, 29 at most. |
| `itd_scale` | 0.5 | Fraction of the physical interaural time difference used by `hybrid`. |
| `ild_limit_db` | 12.0 | Largest level difference between the channels from `hybrid`'s pan law, reached at ±90°; sources in the frame keep their pan. Without it a source at the side is in one ear only, which is uncomfortable on headphones. null = no limit (as `amplitude`). |
| `head_shadow` | 0.5 | Strength of the head-shadow filter in `hybrid` (0 = off, 1 = full spherical-head model). |
| `head_radius` | 0.0875 m | Listener head radius. |
| `rear_cutoff_hz` | 6000 | Low-pass cutoff for a source directly behind the camera. |
| `rear_gain_db` | −2.0 | Extra gain for a source directly behind the camera. |
| `master_gain_db` | 0.0 | Gain on the master sum. |
| `substeps` | 4 | Sub-frames per frame (bake). |
| `pad_seconds` | 3.0 | Padding before and after the shot (covers ~1 km of propagation; the bake warns if a source is farther away in travel time) (bake). |
| `listener` | null | Object name to use instead of the active camera (bake). |
| `quality` | `"standard"` | Fractional-delay interpolation: `standard` (2× oversampled, 6-point polynomial) or `high` (anti-aliased windowed sinc at the output rate: band-limits extreme Doppler; slightly slower below about 30 sources, 20–25 % faster above, [E15](../../research/experiments/E15-option-costs.md)). |
| `occlusion_gain_db` | −12.0 | Transmission through an occluder: gain of a fully occluded source at low frequencies. |
| `occlusion_cutoff_hz` | 1500 | Transmission low-pass: a fully occluded source is a further −3 dB here. |
| `occlusion_rate` | 10.0 | Visibility samples per second in the bake; 0 = no visibility (bake). |
| `occluder_min_size` | 2.0 m | Objects whose bounding-box diagonal is smaller do not occlude (bake). |
| `reverb` | null | Environment: an EFX preset name (`hangar`, `city`, `forest`, `spacestation_hall`, … 113 in all, `soundstage presets`) or an impulse-response file (WAV/FLAC, used as recorded). null = no reverb. |
| `reverb_send_db` | 0.0 | Send level of all sources (added to each source's `reverb_send_db`). |
| `reverb_room_rolloff` | null | Distance rolloff of the send (EFX); null = the preset's room rolloff (0 for nearly all presets). |
| `reverb_send_law` | `"revised"` | `revised`: the send also falls with distance, by 60 dB per `c·T60` within the radius (Barron and Lee) and 6 dB per doubling beyond it, so thousands of distant sources do not fill the reverb. `efx`: the room rolloff alone (constant reverberant level). |
| `reverb_radius_m` | null | Radius of the listener's space for `revised`: within it the revised theory, beyond it spreading. null = `c·T60 / ln(1000)` (city streets 89 m, a hangar 499 m), where both fall equally fast; any other radius gives distant sources less reverb (smaller: a street in an open city; larger: one big hall around all sources). |
| `read_speakers` | true | Read Blender Speaker objects as sources (bake). |
| `instance_limit` | 32 | Per tagged object inside instances: keep at most this many instances, those that come closest to the camera; 0 = all (bake). |
| `detail_voices` | 64 | Far field: per group, at most this many sources (ranked by level per 4 s chunk) get the full processing chain; the others are rendered more cheaply in the far field (no ITD, head shadow or rear low-pass; air absorption by distance band). Lower (16) is faster, null renders every source in full ([signal-model.md](signal-model.md#far-field)). |
| `cull_db` | −40.0 | Culling budget: per group, sources whose summed energy stays this far below the group's are skipped where they do not matter (render: per 4 s chunk, judged on 0.4 s blocks; bake: their visibility rays, 20 dB further below). Lower (−60) is more exact, higher (−20) faster for previews; null = off. Read by the bake and the render ([signal-model.md](signal-model.md#culling)). |

Settings marked *(bake)* are used only by the bake; `render --set` on them changes nothing and
warns. Ranges and the full signal meaning: [signal-model.md](signal-model.md).

## Speaker objects

With `read_speakers` (default), every unmuted Speaker object in the view layer is a source, so a
scene can be set up by hand in Blender's UI without scripts. Each unmuted NLA sound strip is a
trigger frame (Blender creates one when a sound is added to a speaker), so the speaker plays its
sound once at each strip's start. The id is `"<object name>:speaker"`.

| Speaker property | Tag key |
|---|---|
| sound (file; packed sounds are written to `<bake out>/sounds/`) | `sample` |
| NLA sound strip starts | `frame` (`mode = "once"`) |
| volume | `gain_db` = 20 log₁₀(volume) |
| pitch | `pitch` |
| distance reference / maximum (if set) | `ref_distance` / `max_distance` |
| attenuation | `rolloff` |
| scene → Audio → distance model | `distance_model` (inverse, linear, exponent, none; clamped or not alike) |
| cone inner / outer angle, outer cone volume | `cone_inner_deg` / `cone_outer_deg`, `cone_outer_gain_db` |
| mute | skipped |

The speaker's −Z axis is its forward axis, as in Blender. Not used: `volume_min`, `volume_max` (a
warning says so). Anything else (loop instead of once, group, reverb send, occlusion mode) goes in a
custom property `sfx_speaker` on the speaker object: a dict of tag keys that overrides the mapping,
e.g. `{"mode": "loop", "group": "engines"}`. A loop starts at the first strip.

## Tags inside instances

Tagged objects inside collection instances and geometry-nodes instances become one source per
instance, with the instance's world transform. Ids: `"<instancer>/<object>:<index>"` for a
collection instance (an empty with `instance_type = COLLECTION`), `"<instancer>/<object>#<n>:<index>"`
for geometry-nodes and nested instances (`n` from the instance's persistent id). Per tagged object,
at most `instance_limit` instances are kept: those that come closest to the camera over the shot
(30 sampled frames); the bake warns when it drops some. A crowd of 500 instanced cars with an
engine tag thus gives the 32 nearest engines.

Instances are found at the scene's current frame (the frame the .blend was saved at, or the one a
`--run` script sets). An instance that geometry nodes generate only at other frames is not a
source; one that is not generated at some baked samples keeps its last position there, and the bake
warns.

## Occluders

Every rendered mesh object and mesh instance occludes by its oriented bounding box, or, when its
largest connected part (mesh island) fills less than half of that box (a merged mesh: a district of
buildings, brackets around a tower, a railing), by the boxes of its parts; boxes with a diagonal
below `occluder_min_size` drop out. Except:

- objects hidden from rendering (`hide_render`);
- meshes whose materials only emit or pass light: volume-only materials (fog, haze) and surfaces
  built only from Emission, Transparent, Holdout, Add and Mix shaders (light beams, glows,
  holograms). Glass and every other surface occlude;
- text objects (a box over lettering closes the gaps between the letters);
- objects that travel with the listener (their position relative to the camera stays within their
  own size at the shot's first, middle and last frame while they move further than that): the
  camera's vehicle, a cockpit;
- for one source, any box that contains the listener or that source (the emitter's own body, the
  camera's cabin, a box of a merged mesh that is too coarse to tell), and any box that lies beyond
  both (the ground under both, a wall behind both: it reflects instead).

Objects that move between the shot's first, middle and last frame are tracked per sample. A custom
property `sfx_occluder` on the object, or on the collection that is instanced, overrides:

| `sfx_occluder` | Effect |
|---|---|
| missing | as above |
| `False` or `"off"` | never occludes: foliage, fences, nets, grilles, scaffolding and other open structures, helper meshes that render |
| `"mesh"` | uses the object's real triangles (arches, gates, L-shaped or hollow buildings: parts whose box closes an opening); static objects only |

## Helper API (`soundstage/blender/tag.py`)

```python
add_sound(obj, sample, *, mode="loop", frame=None, **params) -> dict
    # Validate params against the table above, append the entry to obj["sfx"], return it.
get_sounds(obj) -> list[dict]
    # The object's entries as plain dicts.
clear_sounds(obj) -> None
set_scene_settings(scene=None, **settings) -> dict
    # Validate and merge into scene["sfx_settings"] (default: bpy.context.scene); return the result.
get_scene_settings(scene=None) -> dict
iter_tagged(scene=None) -> Iterator[tuple[Object, int, dict]]
    # All (object, index, entry) triples of the scene's objects, sorted by object name.
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
- `mode="once"` without `frame` → error; a list of frames for a loop → error.
- `distance_model="linear_clamped"` without `max_distance` → error; `max_distance` below
  `ref_distance` → error.
- `end_frame` before `frame` → error.
- Two sources with the same `id` → error.
- Sample file missing or unreadable → error (bake checks existence; the engine decodes).
- `--skip-invalid` turns errors into warnings and drops the entry.

Storage: lists of dicts are stored as ID property group arrays; checked in Blender 5.2 including
save and reload, `None` values and booleans. A JSON string in `obj["sfx"]` is accepted as well.
