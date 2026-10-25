"""Shared helpers for the Blender-side scripts (bake, scan). Runs inside Blender's Python."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import bpy

PREFIX = "[soundstage]"


def log(msg: str) -> None:
    """Print a line the CLI wrapper picks out of Blender's output."""
    print(f"{PREFIX} {msg}", flush=True)


def script_args() -> list[str]:
    """Arguments after ``--`` on the Blender command line."""
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def run_scripts(paths: list[str]) -> None:
    """Run tagging or generator scripts in the current Blender session (not saved to the .blend)."""
    for p in paths:
        log(f"running {p}")
        runpy.run_path(str(Path(p).resolve()), run_name="__main__")


def activate_scene(name: str | None):
    """Make the named scene the context scene (for --run scripts too); None keeps the active one."""
    if name:
        scene = bpy.data.scenes.get(name)
        if scene is None:
            raise SystemExit(f"scene {name!r} not found; scenes: {', '.join(s.name for s in bpy.data.scenes)}")
        window = bpy.context.window or next(iter(bpy.context.window_manager.windows), None)
        if window is None:
            raise SystemExit("cannot switch scenes: the file has no window")
        window.scene = scene
    return bpy.context.scene


def parse_frames(text: str | None, scene) -> tuple[int, int]:
    """``--frames A-B`` (or ``A``), default the scene's frame range."""
    if not text:
        return scene.frame_start, scene.frame_end
    a, _, b = text.partition("-")
    try:
        first, last = int(a), int(b or a)
    except ValueError:
        raise SystemExit(f"--frames expects A-B, got {text!r}") from None
    if last < first:
        raise SystemExit(f"--frames {text}: the last frame is before the first")
    return first, last


def fps(scene) -> float:
    return scene.render.fps / round(scene.render.fps_base, 6)


def set_frame(scene, frame: float) -> None:
    """Set a (possibly fractional) frame and update the depsgraph."""
    whole = int(frame // 1)
    scene.frame_set(whole, subframe=frame - whole)


def listener_object(scene, name: str | None):
    if name:
        obj = scene.objects.get(name)
        if obj is None:
            raise SystemExit(f"listener object {name!r} not found")
        return obj
    return scene.camera


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def collections_of(obj) -> list[str]:
    return [c.name for c in obj.users_collection]


def blender_version() -> str:
    return ".".join(str(v) for v in bpy.app.version)
