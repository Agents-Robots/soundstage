# 0012. Speaker objects and tags inside instances are sources

- Status: Accepted
- Date: 2026-10-25
- Ticket: #18, #19

## Context

Phase 1 read sources only from `obj["sfx"]` tags on objects in the view layer (ADR 0003), which
suits generator scripts and agents. Two common cases were missing:

- **People working by hand** in Blender use Speaker objects (Add → Speaker, pick a sound, place a
  strip in the timeline): Blender's own, documented way to place sound, previewed in the viewport
  and mixed down by `bpy.ops.sound.mixdown`. Tutorials and add-ons build on it.
- **Instanced assets**: a car or a crowd member tagged once in an asset collection and placed many
  times as collection instances or by geometry nodes. Only the asset object carried the tag, and it
  is not in the view layer.

## Decision

- Every unmuted **Speaker object** is a source: sound, volume, pitch, distances, attenuation, cone,
  and the scene's distance model map to tag keys; each unmuted NLA sound strip is a trigger frame.
  A custom property `sfx_speaker` (a dict of tag keys) overrides the mapping for what Speakers
  cannot express (loops, groups, reverb send, occlusion mode). Scene setting `read_speakers`
  switches this off.
- A tagged object inside an **instance** (collection instance or geometry-nodes instance, found
  through the depsgraph) is one source per instance, with ids derived from the instancer and the
  instance's persistent id. At most `instance_limit` (32) per tagged object, keeping those that come
  closest to the camera; the bake warns about dropped ones.
- Tags remain the primary interface; both paths produce the same resolved source entries, so the
  engine does not know where a source came from.

## Alternatives considered

- **Speakers only** (no tags): loses what Speakers cannot express (loops with phase, sync to
  picture, per-source air absorption and Doppler), and scripted scenes would create objects only to
  carry sound.
- **Tags only**: hand-made scenes would have to type dictionaries into custom properties.
- **Converting Speakers to tags in a separate step**: one more thing to run and keep in sync.
- **All instances, no limit**: a city with 500 instanced cars would render 500 engines, most of them
  inaudible, at 500 times the cost.

## Consequences

- A hand-made scene with Speakers renders with `soundstage bake` and `render` without scripts, and a
  scene that already uses Speakers for Blender's preview gets the physical model for free.
- Speaker semantics (one-shot per strip, Blender's distance model) become part of the interface; a
  Speaker that only had Blender's preview in mind may behave differently (no `volume_min/max`).
- Instance ids depend on the instancer's name and the persistent id; renaming or re-scattering
  changes them, so solo/mute patterns should use globs (`"Traffic/*"`).
