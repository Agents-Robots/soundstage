"""Build the flyby example scene from scratch (runs inside Blender).

A camera dollies slowly forward; a ship flies past from left to right at 30 m/s, closest at about
frame 120; a beacon stands to the left; a crate falls and hits the ground at frame 180. 30 fps,
frames 1-240 (8 s). The sounds are added separately by ``flyby_sounds.py`` at bake time.

    blender -b --factory-startup --python examples/flyby.py -- --save out/flyby.blend
"""

import argparse
import math
import sys
from pathlib import Path

import bpy


def keyframes(obj, path, values):
    """Insert keyframes with linear interpolation (constant speed between keys)."""
    from bpy_extras import anim_utils

    for frame, value in values:
        setattr(obj, path, value)
        obj.keyframe_insert(data_path=path, frame=frame)
    ad = obj.animation_data
    for fc in anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot).fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"


def mesh(op, name, location, **kwargs):
    op(location=location, **kwargs)
    obj = bpy.context.active_object
    obj.name = name
    return obj


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps, scene.render.fps_base = 30, 1.0
    scene.frame_start, scene.frame_end = 1, 240
    scene.render.resolution_x, scene.render.resolution_y = 640, 360

    cam_data = bpy.data.cameras.new("Camera")
    cam = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.rotation_euler = (math.radians(90), 0, 0)  # looking along +Y; camera +X = world +X (right)
    keyframes(cam, "location", [(1, (0, 0, 1.7)), (240, (0, 10, 1.7))])

    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    scene.collection.objects.link(sun)

    mesh(bpy.ops.mesh.primitive_plane_add, "Ground", (0, 40, 0), size=400)

    ship = mesh(bpy.ops.mesh.primitive_cone_add, "Ship", (-120, 30, 4), radius1=2, depth=8)
    ship.rotation_euler = (0, math.radians(90), 0)  # nose along +X, the flight direction
    keyframes(ship, "location", [(1, (-120, 30, 4)), (240, (120, 30, 4))])

    mesh(bpy.ops.mesh.primitive_uv_sphere_add, "Beacon", (-12, 18, 0.5), radius=0.5)

    crate = mesh(bpy.ops.mesh.primitive_cube_add, "Crate", (8, 14, 6), size=1)
    keyframes(crate, "location", [(160, (8, 14, 6)), (180, (8, 14, 0.5))])

    ambience = bpy.data.objects.new("Ambience", None)
    scene.collection.objects.link(ambience)
    scene.frame_set(1)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--save", default="out/flyby.blend")
    args = p.parse_args(argv)
    build()
    path = Path(args.save).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    print(f"saved {path}")
