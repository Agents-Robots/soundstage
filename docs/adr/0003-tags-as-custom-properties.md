# 0003. Sound sources as custom-property tags on objects

- Status: Accepted
- Date: 2026-10-25
- Ticket: —

## Context

Scenes are built by generator scripts. Sounds belong to things in the scene (a ship's engine, a
door, a beacon) and must move with them. They need to be declared where those things are created,
reproducibly (NFR-1), with more parameters than Blender's Speaker objects offer (offsets, groups,
sync to picture, loop phase, occlusion settings, later animated parameters).

## Decision

- Each sound is a dict in a list stored as the custom property `obj["sfx"]` on the object (not on
  its data block). Scene-wide settings go in `scene["sfx_settings"]`.
- Generator scripts write tags through `soundstage.blender.tag.add_sound(...)`, which validates
  keys against one schema (`soundstage/blender/schema.py`). The schema, defaults and meaning are
  specified in [spec/tagging.md](../spec/tagging.md).
- Native Speaker objects are additionally read as sources (Phase 3, FR-8), so sounds can also be
  placed in the UI.

## Alternatives considered

- **Speaker objects only**: visible in the UI and used by Blender's own mixdown, but one sound per
  speaker, extra objects to parent and keep in sync, a fixed parameter set, and sound data blocks
  to manage. Kept as a secondary input.
- **A separate cue file** (JSON/YAML next to the scripts): independent of Blender, but positions
  must still come from Blender, and objects are referenced by name across two places that drift
  apart when scripts change.
- **Custom property group via a registered add-on** (`bpy.props.PointerProperty`): typed UI
  fields, but needs an add-on to be registered in every session, including headless bakes with
  `--factory-startup`.

## Consequences

- Tags are saved in the .blend, visible and editable in Object Properties → Custom Properties,
  and readable by any script without an add-on.
- Object-level storage lets linked duplicates (shared mesh) carry different sounds.
- Typos in keys are only caught by validation (`add_sound` and the bake), hence the strict
  unknown-key check.
- Storage of lists of dicts as ID properties must be confirmed in Blender 5.2 (Phase 0); fallback
  is a JSON string in the same property, which the bake accepts too.
