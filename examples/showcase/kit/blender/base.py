"""Scene setup, palette, materials, keyframes and cameras shared by every section (in Blender).

A section's ``build.py`` calls ``new_scene`` first, builds its set and action with the models and
the town, adds overlays, and ends with ``finish``, which binds the cameras to markers, writes the
sound settings and the manifest, and saves the .blend.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from bpy_extras import anim_utils
from mathutils import Vector

from .. import story

REPO = Path(__file__).resolve().parents[4]
SOUNDS = REPO / "out" / "showcase" / "sounds"
EYE = 1.6
"""Camera height of a person (m)."""

PALETTE = {
    # overlays (sections/README.md, P4)
    "bg": "#12161d", "text": "#f3f0ea", "accent": "#f5a524", "muted": "#8b929c", "panel": "#0b0e13",
    "code": "#d9e1ea", "black": "#000000",
    # town
    "asphalt": "#3d4046", "kerb": "#9a978f", "pavement": "#a39d92", "paving": "#b7ab95", "grass": "#6f9a52",
    "marking": "#e8e6df", "roof": "#8a4a3a", "roof_dark": "#5b4a46", "wall_1": "#e2d3b5", "wall_2": "#c9b8a0",
    "wall_3": "#d9c2a6", "wall_4": "#b9c0b5", "wall_5": "#e6c9a1", "window": "#2b3440", "window_lit": "#ffc777",
    "stone": "#b8b1a2", "slate": "#4c5560", "wood": "#7a5a3c", "metal": "#5c6066", "bell": "#b08d3c",
    "leaf": "#4f7f45", "leaf_dark": "#3f6b3a", "trunk": "#5b4636", "lamp": "#fff1c9",
    # vehicles and people
    "tyre": "#1c1f24", "rim": "#9aa0a8", "glass": "#2b3a4a", "car_red": "#b33a2e", "car_blue": "#3a5f9c",
    "car_grey": "#8c9196", "car_green": "#4c7a5a", "white": "#f1efe9", "ambulance_red": "#d6402f",
    "siren_blue": "#3d7df0", "headlight": "#fff6dc", "taillight": "#c41e1e", "truck_cab": "#2f6db0",
    "truck_box": "#d8d4c8", "scooter": "#d24a3a", "skin": "#e0b08c", "shirt": "#3f6e9e", "trousers": "#2f3238",
    "jacket": "#7d4e3a",
    # lake
    "water": "#2b4257", "hill": "#33473a", "spark_red": "#ff5a3c", "spark_gold": "#ffc24a", "spark_blue": "#7fb2ff",
    "bolt": "#e8eeff",
    # doppler
    "race_blue": "#2456b8", "prop_blur": "#c9ccd1", "ballast": "#8d877c", "wood_dark": "#4a3a2c", "rail": "#7d8187",
    "cab": "#4d5a52", "cab_dark": "#262b2a", "field": "#a7a25a", "runway": "#4a4c50", "hangar": "#9aa3a8",
    "windsock": "#f07a2a", "armco": "#b9bdc2", "kerb_red": "#c8342b",
    # screen
    "court": "#3f6f9f", "court_out": "#4f8a5c", "net": "#22262b", "ball": "#d9ea3c", "racket": "#2a2e35",
    "fence": "#3c5a48", "shirt_white": "#eceae4", "shirt_red": "#b8443a",
    # directivity
    "apron": "#8f9094", "apron_line": "#e3c341", "jet_white": "#eef0f2", "jet_trim": "#2f4f7f", "fan": "#30343a",
    "nozzle": "#4a4d52",
    # occlusion
    "bike_green": "#2f7a4f", "bike_helmet": "#d8d6cf", "accordion": "#a3262a", "bellows": "#26282c",
    # reverb
    "room_wall": "#e9dfcf", "parquet": "#9a6b43", "rug": "#6d4a5e", "sofa": "#56708a", "sky_window": "#e8f2ff",
    "gym_wall": "#d7d2c4", "gym_floor": "#c99a5b", "gym_ceiling": "#9aa0a6", "gym_line": "#f2f0ea",
    "rim_orange": "#e0662a", "basketball": "#d0601f", "nave_floor": "#8f8678", "nave_ceiling": "#6d6458",
    "stone_light": "#cfc6b4", "stained": "#7f9be0", "rug_red": "#8a2b2b", "court_asphalt": "#4c6f5a",
    # finale
    "loco": "#a8322a", "loco_dark": "#2a2d31", "coach": "#3c6a8f",
}


def linear(hex_colour: str) -> tuple[float, float, float]:
    """sRGB hex to linear RGB (what Blender's colour sockets take)."""
    h = hex_colour.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return tuple(out)


def colour(name: str) -> tuple[float, float, float, float]:
    return (*linear(PALETTE.get(name, name)), 1.0)


# --- scene ---------------------------------------------------------------------------------------

def new_scene(section: story.Section) -> bpy.types.Scene:
    """Empty file with the showcase's format (rule C3): 30 fps, 1920 x 1080, Cycles, Standard view."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = section.key
    scene.render.fps, scene.render.fps_base = story.FPS, 1.0
    scene.frame_start, scene.frame_end = 1, section.frame_end
    scene.render.resolution_x, scene.render.resolution_y = story.RESOLUTION
    scene.render.resolution_percentage = 100
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 4
    scene.cycles.transparent_max_bounces = 32
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_motion_blur = False
    _materials.clear()
    return scene


def world(time_of_day: str) -> None:
    """Sky gradient and sun for ``day`` or ``dusk``."""
    scene = bpy.context.scene
    w = bpy.data.worlds.new(time_of_day)
    scene.world = w
    nt = w.node_tree
    bg = nt.nodes["Background"]
    coords = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(coords.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    stops = {"day": [(0.5, "#dfe9ee"), (0.62, "#a9cbe6"), (1.0, "#6fa3d6")],
             "dusk": [(0.5, "#3a2f4a"), (0.53, "#c98a6a"), (0.6, "#4a5a86"), (1.0, "#141a33")]}[time_of_day]
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = stops[0][0], colour(stops[0][1])
    els[1].position, els[1].color = stops[-1][0], colour(stops[-1][1])
    for pos, c in stops[1:-1]:
        e = els.new(pos)
        e.color = colour(c)
    bg.inputs["Strength"].default_value = {"day": 1.0, "dusk": 0.6}[time_of_day]
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    scene.collection.objects.link(sun)
    if time_of_day == "day":
        sun.data.energy, sun.data.color = 3.0, linear("#fff3e0")
        sun.rotation_euler = (math.radians(40), 0, math.radians(-35))
    else:
        sun.data.energy, sun.data.color = 0.35, linear("#ffb27a")
        sun.rotation_euler = (math.radians(84), 0, math.radians(-100))
    sun.data.angle = math.radians(2)


# --- materials -----------------------------------------------------------------------------------

_materials: dict[str, bpy.types.Material] = {}


def surface(name: str, roughness: float = 0.75, emission: str | None = None, strength: float = 0.0):
    """Flat Principled material in a palette colour (cached by name)."""
    key = f"{name}|{emission}|{strength}"
    if key in _materials:
        return _materials[key]
    mat = bpy.data.materials.new(name)
    p = mat.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = colour(name)
    p.inputs["Roughness"].default_value = roughness
    if emission:
        p.inputs["Emission Color"].default_value = colour(emission)
        p.inputs["Emission Strength"].default_value = strength
    _materials[key] = mat
    return mat


def glow(name: str, colour_name: str, strength: float = 1.0):
    """A material of its own whose emission strength can be keyed (lights that blink)."""
    mat = bpy.data.materials.new(name)
    p = mat.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = colour(colour_name)
    p.inputs["Emission Color"].default_value = colour(colour_name)
    p.inputs["Emission Strength"].default_value = strength
    return mat


def emission_socket(mat):
    return mat.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]


# --- objects -------------------------------------------------------------------------------------

def collection(name: str):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def link(obj, coll=None):
    (coll or bpy.context.scene.collection).objects.link(obj)
    return obj


def empty(name: str, location=(0, 0, 0), parent=None, coll=None):
    obj = link(bpy.data.objects.new(name, None), coll)
    obj.empty_display_size = 0.3
    obj.parent = parent
    obj.location = tuple(location)
    return obj


def mesh_object(name: str, verts, faces, material, parent=None, location=(0, 0, 0), coll=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.update()
    if isinstance(material, (list, tuple)):
        for m in material:
            me.materials.append(m)
    else:
        me.materials.append(material)
    obj = link(bpy.data.objects.new(name, me), coll)
    obj.parent = parent
    obj.location = tuple(location)
    return obj


def box_geometry(sx: float, sy: float, sz: float, cx=0.0, cy=0.0, cz=0.0, offset: int = 0):
    """Vertices and faces of an axis-aligned box centred at (cx, cy, cz)."""
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    verts = [(cx + x, cy + y, cz + z) for z in (-hz, hz) for y in (-hy, hy) for x in (-hx, hx)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return verts, [tuple(i + offset for i in f) for f in faces]


def box(name: str, size, location, material, parent=None, coll=None):
    v, f = box_geometry(*size)
    return mesh_object(name, v, f, material, parent, location, coll)


def cylinder_geometry(radius: float, depth: float, axis: str = "Z", sides: int = 12, offset: int = 0,
                      radius_top: float | None = None):
    rt = radius if radius_top is None else radius_top
    verts = []
    for z, r in ((-depth / 2, radius), (depth / 2, rt)):
        for i in range(sides):
            a = 2 * math.pi * i / sides
            p = (r * math.cos(a), r * math.sin(a), z)
            verts.append({"Z": p, "X": (p[2], p[0], p[1]), "Y": (p[0], p[2], p[1])}[axis])
    faces = [tuple(range(sides - 1, -1, -1)), tuple(range(sides, 2 * sides))]
    faces += [(i, (i + 1) % sides, sides + (i + 1) % sides, sides + i) for i in range(sides)]
    if axis == "Y":
        faces = [tuple(reversed(f)) for f in faces]
    return verts, [tuple(i + offset for i in f) for f in faces]


def cylinder(name: str, radius: float, depth: float, location, material, axis: str = "Z", sides: int = 12,
             parent=None, radius_top: float | None = None, coll=None):
    v, f = cylinder_geometry(radius, depth, axis, sides, radius_top=radius_top)
    return mesh_object(name, v, f, material, parent, location, coll)


def sphere(name: str, radius: float, location, material, parent=None, segments: int = 12, rings: int = 8, coll=None):
    verts = [(0, 0, radius)]
    for j in range(1, rings):
        th = math.pi * j / rings
        for i in range(segments):
            ph = 2 * math.pi * i / segments
            verts.append((radius * math.sin(th) * math.cos(ph), radius * math.sin(th) * math.sin(ph), radius * math.cos(th)))
    verts.append((0, 0, -radius))
    faces = [(0, 1 + i, 1 + (i + 1) % segments) for i in range(segments)]
    for j in range(rings - 2):
        a, b = 1 + j * segments, 1 + (j + 1) * segments
        faces += [(a + i, b + i, b + (i + 1) % segments, a + (i + 1) % segments) for i in range(segments)]
    last = len(verts) - 1
    a = 1 + (rings - 2) * segments
    faces += [(a + i, last, a + (i + 1) % segments) for i in range(segments)]
    faces = [tuple(reversed(f)) for f in faces]
    return mesh_object(name, verts, faces, material, parent, location, coll)


def no_occlusion(obj) -> None:
    """Mark an object (and its children) as not occluding sound (``sfx_occluder = False``)."""
    for o in [obj, *obj.children_recursive]:
        if o.type == "MESH":
            o["sfx_occluder"] = False


# --- animation -----------------------------------------------------------------------------------

def key(target, path: str, frame: float, value, interpolation: str = "LINEAR") -> None:
    """One keyframe; the interpolation applies from this key to the next. Set on the key itself:
    ``keyframe_insert`` ignores the preference for new keys in background mode (all Bezier)."""
    setattr(target, path, value)
    target.keyframe_insert(data_path=path, frame=frame)
    ad = target.id_data.animation_data
    full = target.path_from_id(path)
    for fc in anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot).fcurves:
        if fc.data_path == full:
            for k in fc.keyframe_points:
                if abs(k.co.x - frame) < 1e-3:
                    k.interpolation = interpolation


def runs(target, path: str, runs_: list[list[tuple[float, object]]]) -> None:
    """Keyed runs: linear within a run, held after its last key until the next run starts (a hard
    cut between passes restarts the action)."""
    for run in runs_:
        for i, (frame, value) in enumerate(run):
            key(target, path, frame, value, "CONSTANT" if i == len(run) - 1 else "LINEAR")


def visible(obj, windows: list[tuple[float, float]], recursive: bool = True) -> None:
    """Rendered only within the frame windows [first, last]."""
    for o in [obj, *(obj.children_recursive if recursive else [])]:
        key(o, "hide_render", 0, True, "CONSTANT")
        key(o, "hide_viewport", 0, True, "CONSTANT")
        for a, b in windows:
            for path in ("hide_render", "hide_viewport"):
                key(o, path, a, False, "CONSTANT")
                key(o, path, b + 1, True, "CONSTANT")


def frames_between(a: float, b: float) -> list[float]:
    """a, every whole frame strictly between, and b."""
    return sorted({a, *range(math.floor(a) + 1, math.ceil(b)), b})


# --- cameras -------------------------------------------------------------------------------------

HUD_W, HUD_H = 0.72, 0.405
"""Size of the frame at the overlay root (lens / 50 m in front of a 36 mm camera)."""


def camera(name: str, location, target=None, lens: float = 35.0, rotation=None, coll=None):
    """A camera with its overlay root (``cam["hud"]``): an empty at lens / 50 m in front of it, where
    the frame is always 0.72 x 0.405 m."""
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.sensor_fit = "HORIZONTAL"
    data.sensor_width = 36.0
    data.clip_start = 0.05
    data.clip_end = 3000.0
    cam = link(bpy.data.objects.new(name, data), coll)
    cam.location = tuple(location)
    if rotation is not None:
        cam.rotation_euler = rotation
    else:
        look(cam, target)
    hud = empty(f"{name}.hud", (0, 0, -lens / 50), parent=cam, coll=coll)
    cam["hud"] = hud.name
    return cam


def hud_of(cam):
    return bpy.data.objects[cam["hud"]]


def look(obj, target, roll_deg: float = 0.0) -> None:
    rot = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    obj.rotation_euler = rot
    if roll_deg:
        obj.rotation_euler.rotate_axis("Z", math.radians(roll_deg))


def aim(location, yaw_deg: float, pitch_deg: float = 0.0):
    """Camera rotation looking along the compass direction ``yaw_deg`` (0 = +Y, 90 = -X: counter-
    clockwise seen from above), tilted up by ``pitch_deg``."""
    return (math.radians(90 + pitch_deg), 0.0, math.radians(yaw_deg))


# --- finishing -----------------------------------------------------------------------------------

def finish(section: story.Section, shots: list[tuple[int, object]], out_dir: Path, settings: dict | None = None) -> Path:
    """Bind cameras to markers, write the sound settings and the manifest, save the .blend."""
    scene = bpy.context.scene
    scene.timeline_markers.clear()
    for frame, cam in sorted(shots, key=lambda s: s[0]):
        m = scene.timeline_markers.new(f"{cam.name}@{frame}", frame=frame)
        m.camera = cam
    scene.camera = sorted(shots, key=lambda s: s[0])[0][1]
    from soundstage.blender import tag
    tag.set_scene_settings(scene, samples_root=str(SOUNDS) + "/", **({"reverb": section.reverb} if section.reverb else {}),
                           **(settings or {}))
    scene.frame_set(1)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "section.json").write_text(json.dumps(section.manifest(), indent=1) + "\n")
    path = out_dir / f"{section.key}.blend"
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=True)
    print(f"saved {path}")
    return path
