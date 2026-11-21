"""Blender-side code: runs inside Blender's Python (bpy, stdlib, Blender's bundled numpy).

- ``tag``: helper imported by scene generator scripts to attach sounds to objects.
- ``schema``: tag and scene-settings schema (keys, types, defaults, ranges), shared with the engine.
- ``bake``: script run with ``blender -b ... --python bake.py -- <args>`` to write the scene file.

Scripts run by ``bake --run`` import ``tag`` directly; generator scripts run in Blender on their own
import it by path, the folder printed by ``soundstage blender-path``::

    import sys
    sys.path.insert(0, "/path/to/soundstage")
    from soundstage.blender import tag
"""
