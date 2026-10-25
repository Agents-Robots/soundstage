"""Tag helper for scene generator scripts: attach sounds to Blender objects.

Writes plain data into custom properties, so tags are saved in the .blend, visible in Object
Properties -> Custom Properties, and readable without an add-on (ADR 0003).

Planned interface (docs/spec/tagging.md):

- ``add_sound(obj, sample, *, mode="loop", frame=None, **params) -> list[dict]``:
  validate against ``schema``, append one entry to ``obj["sfx"]`` (several if ``frame`` is a list),
  return the entries.
- ``clear_sounds(obj) -> None``: remove all tags from an object.
- ``set_scene_settings(scene=None, **settings) -> dict``: merge into ``scene["sfx_settings"]``.
- ``iter_tagged(scene=None) -> Iterator[tuple[Object, dict]]``: all (object, entry) pairs in the
  scene's view layer; used by ``bake``.

Imports only bpy and the standard library. Phase 1.
"""
