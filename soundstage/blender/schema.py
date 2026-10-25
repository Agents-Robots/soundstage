"""Schema of sound tags (``obj["sfx"]`` entries) and scene settings (``scene["sfx_settings"]``).

The single source of defaults (NFR-8): every key with its type, default, allowed values or range,
and the phase that introduces it. Used by ``tag.add_sound`` for validation, by ``bake`` to resolve
defaults into the scene file, and by the engine for ``--set`` overrides and for scene files written
without Blender.

Stdlib only (no bpy, no numpy), so both Blender and the venv can import it.

Content is specified in docs/spec/tagging.md (tag keys and scene settings) and
docs/spec/signal-model.md (meaning of each constant). Planned interface:

- ``SOURCE_KEYS``: mapping key -> field description (type, default, range, phase).
- ``SCENE_SETTINGS``: mapping key -> field description.
- ``validate_source(entry) -> list[str]``: error messages, empty if valid.
- ``resolve_source(entry, settings) -> dict``: entry with all defaults filled in.
- ``validate_settings(settings) -> list[str]``, ``resolve_settings(settings) -> dict``.

Phase 1.
"""
