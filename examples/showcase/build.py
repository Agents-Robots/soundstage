"""Build the feature showcase scene from scratch (runs inside Blender).

One scene, one timeline: every chapter of ``storyboard.py`` has its own stage (ground, simple
shapes, its own cameras) 3 km from the others, and timeline markers bound to the cameras switch
between them. Titles, pass labels and the top-view radar are emissive text and shapes parented to
the cameras. Objects light up while they sound. The sound tags are set here too, so the saved .blend
bakes without ``--run``; render settings that change per pass live in the storyboard.

    blender -b --factory-startup --python examples/showcase/build.py -- --save out/showcase/showcase.blend
"""

import argparse
import math
import sys
from pathlib import Path

import bpy
from bpy_extras import anim_utils
from mathutils import Vector

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

import storyboard as sb  # noqa: E402

from soundstage.blender import tag  # noqa: E402

FPS = sb.FPS
EYE = 1.6  # camera height (m)
GLOW = 4.0  # emission strength of a sounding object
SPACING = 3000.0  # m between stages
HUD_HALF = (0.36, 0.2025)  # half the frame at the HUD's distance (lens / 50 m): 16:9
RADAR_CENTER, RADAR_R = (0.262, -0.098), 0.07
C = {
    "red": (0.9, 0.18, 0.12), "orange": (0.95, 0.5, 0.08), "yellow": (0.95, 0.82, 0.15),
    "green": (0.25, 0.8, 0.3), "blue": (0.15, 0.4, 0.95), "purple": (0.6, 0.25, 0.9),
    "cyan": (0.1, 0.8, 0.85), "grey": (0.3, 0.3, 0.33), "white": (0.9, 0.9, 0.9),
}

switches: list[tuple[float, object]] = []  # (frame, camera) for the markers
huds: dict[str, object] = {}  # camera name -> HUD root
occluders: set[str] = set()  # meshes that keep blocking sound; every other mesh gets sfx_occluder = False
materials: dict[str, object] = {}


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


def segments(target, path: str, runs: list[list[tuple[float, object]]]) -> None:
    """Keyframed runs: linear within a run, held after its last key until the next run jumps in."""
    for run in runs:
        for i, (frame, value) in enumerate(run):
            key(target, path, frame, value, "CONSTANT" if i == len(run) - 1 else "LINEAR")


def sampled(fn, a: float, b: float) -> list[tuple[float, object]]:
    """fn(frame) at every frame from a to b, including both ends (fractional ends allowed)."""
    frames = [a, *range(math.floor(a) + 1, math.ceil(b)), b]
    return [(f, fn(f)) for f in sorted(set(frames))]


def visible(obj, windows: list[tuple[float, float]]) -> None:
    """Rendered only within the given frame windows [first, last]."""
    key(obj, "hide_render", sb.FRAME_START - 1, True, "CONSTANT")
    key(obj, "hide_viewport", sb.FRAME_START - 1, True, "CONSTANT")
    for a, b in windows:
        for path in ("hide_render", "hide_viewport"):
            key(obj, path, a, False, "CONSTANT")
            key(obj, path, b + 1, True, "CONSTANT")


def lights(obj, on: list[tuple[float, float]] = (), flashes: list[float] = (), decay_s: float = 0.25) -> None:
    """Emission of the object's own material: ramps for (start, end) of loops, a decaying flash
    at each one-shot frame."""
    socket = obj.active_material.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
    keys = [(sb.FRAME_START - 1, 0.0, "CONSTANT")]
    for a, b in on:
        keys += [(a, 0.0, "LINEAR"), (a + 0.15 * FPS, GLOW, "LINEAR"), (b, GLOW, "LINEAR"), (b + 0.3 * FPS, 0.0, "CONSTANT")]
    flashes = sorted(flashes)
    for i, f in enumerate(flashes):
        gap = flashes[i + 1] - f if i + 1 < len(flashes) else 1e9
        keys += [(f, GLOW, "LINEAR"), (f + min(decay_s * FPS, 0.8 * gap), 0.0, "CONSTANT")]
    for frame, value, interpolation in sorted(keys, key=lambda k: k[0]):
        key(socket, "default_value", frame, value, interpolation)


# --- materials -----------------------------------------------------------------------------------

def surface(name: str, color, alpha: float = 1.0, glow: bool = False):
    """Principled material; a glowing object gets its own copy so its emission can be keyed."""
    if not glow and name in materials:
        return materials[name]
    mat = bpy.data.materials.new(name)
    p = mat.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1.0)
    p.inputs["Roughness"].default_value = 0.6
    p.inputs["Emission Color"].default_value = (*color, 1.0)
    p.inputs["Emission Strength"].default_value = 0.0
    if alpha < 1.0:
        p.inputs["Alpha"].default_value = alpha
        mat.surface_render_method = "BLENDED"
    if not glow:
        materials[name] = mat
    return mat


def flat(name: str, color, alpha: float = 1.0, strength: float = 1.0):
    """Light-only material for overlays (Emission, mixed with Transparent below alpha 1)."""
    if name in materials:
        return materials[name]
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    out = nt.nodes["Material Output"]
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1.0)
    em.inputs["Strength"].default_value = strength
    if alpha < 1.0:
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        mix.inputs["Fac"].default_value = alpha
        nt.links.new(tr.outputs[0], mix.inputs[1])
        nt.links.new(em.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
        mat.surface_render_method = "BLENDED"
    else:
        nt.links.new(em.outputs[0], out.inputs["Surface"])
    materials[name] = mat
    return mat


def checker():
    """Ground: a dark 2 m checker, so that distance and motion read."""
    if "ground" in materials:
        return materials["ground"]
    mat = bpy.data.materials.new("ground")
    nt = mat.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Roughness"].default_value = 0.9
    tc = nt.nodes.new("ShaderNodeTexCoord")
    ck = nt.nodes.new("ShaderNodeTexChecker")
    ck.inputs["Scale"].default_value = 0.5
    ck.inputs["Color1"].default_value = (0.1, 0.1, 0.11, 1)
    ck.inputs["Color2"].default_value = (0.14, 0.14, 0.15, 1)
    nt.links.new(tc.outputs["Object"], ck.inputs["Vector"])
    nt.links.new(ck.outputs["Color"], p.inputs["Base Color"])
    materials["ground"] = mat
    return mat


# --- objects -------------------------------------------------------------------------------------

def link(obj):
    bpy.context.view_layer.active_layer_collection.collection.objects.link(obj)
    return obj


def mesh(op, name: str, location, color=None, glow: bool = False, material=None, **kwargs):
    op(location=tuple(location), **kwargs)
    obj = bpy.context.active_object
    obj.name = name
    mat = material or (surface(name if glow else f"m_{color}", C[color], glow=glow) if color else None)
    if mat:
        obj.data.materials.append(mat)
    return obj


def empty(name: str, location, parent=None):
    obj = link(bpy.data.objects.new(name, None))
    obj.parent = parent
    obj.location = tuple(location)
    return obj


def text(name: str, body: str, location, size: float, parent=None, align: str = "CENTER", rotation=(0, 0, 0),
         material=None):
    curve = bpy.data.curves.new(name, "FONT")
    curve.body = body
    curve.size = size
    curve.align_x = align
    curve.align_y = "CENTER"
    obj = link(bpy.data.objects.new(name, curve))
    obj.parent = parent
    obj.location = tuple(location)
    obj.rotation_euler = rotation
    obj.data.materials.append(material or flat("hud_white", (1, 1, 1)))
    obj.visible_shadow = False
    return obj


def ground(name: str, origin: Vector, size: float = 300.0):
    return mesh(bpy.ops.mesh.primitive_plane_add, name, origin, material=checker(), size=size)


def stage(key: str, index: int, size: float = 300.0) -> Vector:
    """A collection for the chapter and its ground, on a 5-wide grid of stages."""
    coll = bpy.data.collections.new(key)
    bpy.context.scene.collection.children.link(coll)
    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[key]
    origin = Vector(((index % 5 - 2) * SPACING, (index // 5 - 2) * SPACING, 0.0))
    ground(f"{key}_ground", origin, size)
    return origin


def look(obj, target) -> None:
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def camera(name: str, location, target, lens: float = 35.0):
    """A camera with its HUD root: an empty at lens / 50 m in front of it, where the frame is
    always 0.72 x 0.405 m whatever the lens (keep it there when the lens is animated)."""
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.clip_start = 0.02
    data.clip_end = 2500.0
    cam = link(bpy.data.objects.new(name, data))
    cam.location = tuple(location)
    look(cam, target)
    huds[name] = empty(f"{name}_hud", (0, 0, -lens / 50), parent=cam)
    return cam


def hud_mesh(op, name: str, parent, location, material, scale=(1, 1, 1), rotation=(0, 0, 0), **kwargs):
    op(**kwargs)
    obj = bpy.context.active_object
    obj.name = name
    obj.parent = parent
    obj.location = tuple(location)
    obj.scale = scale
    obj.rotation_euler = rotation
    obj.data.materials.append(material)
    obj.visible_shadow = False
    return obj


# --- overlays ------------------------------------------------------------------------------------

def title_card(cam, title: str, subtitle: str, window: tuple[float, float], big: bool = False) -> None:
    root = huds[cam.name]
    parts = [hud_mesh(bpy.ops.mesh.primitive_plane_add, f"{cam.name}_card", root, (0, 0, -0.002),
                      flat("hud_card", (0, 0, 0), alpha=0.85), scale=(HUD_HALF[0] * 2.2, HUD_HALF[1] * 2.2, 1), size=1),
             text(f"{cam.name}_title", title, (0, 0.035 if big else 0.03, 0), 0.05 if big else 0.032, root),
             text(f"{cam.name}_subtitle", subtitle, (0, -0.045 if big else -0.035, 0), 0.0135, root)]
    for obj in parts:
        visible(obj, [window])


def label(cam, chapter_title: str, body: str, window: tuple[float, float], name: str) -> None:
    root = huds[cam.name]
    parts = [hud_mesh(bpy.ops.mesh.primitive_plane_add, f"{name}_strip", root, (0, -0.178, -0.001),
                      flat("hud_strip", (0, 0, 0), alpha=0.6), scale=(HUD_HALF[0] * 2.2, 0.042, 1), size=1),
             text(f"{name}_label", body, (0, -0.178, 0), 0.0135, root),
             text(f"{name}_chapter", chapter_title.splitlines()[0], (-0.345, 0.185, 0), 0.0105, root, align="LEFT")]
    for obj in parts:
        visible(obj, [window])


def radar(cam, range_m: float, windows: list[tuple[float, float]], fov_deg: float):
    """Top view in the lower right corner: the listener at the centre facing up, the camera's field
    of view, a ring at ``range_m``. Returns its root and metres -> radar units."""
    root = empty(f"{cam.name}_radar", (*RADAR_CENTER, -0.004), parent=huds[cam.name])
    white = flat("radar_line", (0.8, 0.8, 0.8), alpha=0.6)
    parts = [
        hud_mesh(bpy.ops.mesh.primitive_circle_add, f"{cam.name}_radar_disc", root, (0, 0, -0.001),
                 flat("radar_disc", (0.02, 0.03, 0.05), alpha=0.75), radius=RADAR_R, vertices=64, fill_type="NGON"),
        hud_mesh(bpy.ops.mesh.primitive_torus_add, f"{cam.name}_radar_rim", root, (0, 0, 0), white,
                 major_radius=RADAR_R, minor_radius=0.0009, major_segments=96, minor_segments=6),
        hud_mesh(bpy.ops.mesh.primitive_circle_add, f"{cam.name}_radar_me", root, (0, 0, 0.0005),
                 flat("hud_white", (1, 1, 1)), radius=0.005, vertices=3, fill_type="NGON"),
        text(f"{cam.name}_radar_text", f"top view, {range_m:g} m", (0, -RADAR_R - 0.009, 0), 0.0075, root),
    ]
    for side in (-1, 1):
        a = math.radians(fov_deg / 2) * side
        parts.append(hud_mesh(bpy.ops.mesh.primitive_plane_add, f"{cam.name}_radar_fov{side}", root,
                              (-math.sin(a) * RADAR_R / 2, math.cos(a) * RADAR_R / 2, 0), white,
                              scale=(0.0012, RADAR_R, 1), rotation=(0, 0, a), size=1))
    for obj in parts:
        visible(obj, windows)
    return root, RADAR_R / range_m


def dot(name: str, parent, location, color: str, windows, radius: float = 0.004):
    obj = hud_mesh(bpy.ops.mesh.primitive_circle_add, name, parent, location, flat(f"dot_{color}", C[color], strength=2),
                   radius=radius, vertices=24, fill_type="NGON")
    visible(obj, windows)
    return obj


def ring(name: str, parent, location, color: str):
    return hud_mesh(bpy.ops.mesh.primitive_torus_add, name, parent, location, flat(f"dot_{color}", C[color], strength=2),
                    major_radius=1.0, minor_radius=0.025, major_segments=96, minor_segments=6)


# --- chapters ------------------------------------------------------------------------------------
# Each builds its stage and returns, per pass, the cameras that show it (the first one is cut to at
# the start of the pass). Sound ids are <chapter>.<pass>.<name>, so a pass renders with --solo.

ID = sb.source_id


ball_runs: dict[str, list] = {}


def bounce(obj, floor: Vector, window, release_s: float, height: float, until_s: float) -> list[float]:
    """Drop from ``height`` above ``floor`` (the centre at contact) at ``release_s`` and bounce until
    ``until_s``; the keys are collected in ``ball_runs`` (several passes can key one object, then
    ``segments(obj, "location", ball_runs.pop(obj.name))``). Returns the contact frames."""
    g, restitution = 9.81, 0.7
    t_hit = release_s + math.sqrt(2 * height / g)
    v = math.sqrt(2 * g * height)
    pts = [(window.first, floor + Vector((0, 0, height))), (window.at(release_s), floor + Vector((0, 0, height)))]
    pts += [(window.at(s), floor + Vector((0, 0, height - 0.5 * g * (s - release_s) ** 2)))
            for s in frange(release_s, t_hit)]
    contacts = []
    while t_hit < until_s and v > 1.0:
        contacts.append(t_hit)
        pts.append((window.at(t_hit), floor.copy()))
        v *= restitution
        t_next = t_hit + 2 * v / g
        pts += [(window.at(s), floor + Vector((0, 0, v * (s - t_hit) - 0.5 * g * (s - t_hit) ** 2)))
                for s in frange(t_hit, t_next)]
        t_hit = t_next
    pts.append((window.at(t_hit), floor.copy()))
    pts.sort(key=lambda k: k[0])
    ball_runs.setdefault(obj.name, []).append(pts)
    return [window.at(c) for c in contacts]


def frange(a: float, b: float) -> list[float]:
    """Times strictly between a and b on the frame grid."""
    n = math.floor(a * FPS) + 1
    out = []
    while n / FPS < b - 1e-9:
        if n / FPS > a + 1e-9:
            out.append(n / FPS)
        n += 1
    return out



def ch_intro(t, o):
    cam = camera("intro_cam", o + Vector((0, -14, 3)), o + Vector((0, 0, 1.2)))
    mesh(bpy.ops.mesh.primitive_uv_sphere_add, "intro_sphere", o + Vector((-3.2, 0, 1)), "red", radius=1)
    mesh(bpy.ops.mesh.primitive_cube_add, "intro_cube", o + Vector((0, 1.5, 1)), "blue", size=2)
    cone = mesh(bpy.ops.mesh.primitive_cone_add, "intro_cone", o + Vector((3.2, 0, 1)), "yellow", radius1=1, depth=2)
    cone.rotation_euler = (0, 0, 0.3)
    segments(cam, "location", [[(sb.FRAME_START, cam.location.copy()),
                                (sb.frame_end(), cam.location + Vector((0, 4, 0)))]])
    return cam


def ch_sources(t, o):
    w = t.passes
    cams = {}

    # loop: a cube hums from 1.0 to 5.0 s
    a = o + Vector((0, 0, 0))
    cams["loop"] = camera("sources_loop_cam", a + Vector((0, 0, EYE)), a + Vector((0, 8, 0.8)))
    cube = mesh(bpy.ops.mesh.primitive_cube_add, "sources_hum_cube", a + Vector((0, 8, 0.6)), "orange", glow=True, size=1.2)
    on, off = w["loop"].at(1.0), w["loop"].at(5.0)
    tag.add_sound(cube, "engine_hum.wav", id=ID("sources", "loop", "cube"), frame=on, end_frame=off, fade_in=0.4,
                  fade_out=0.6, ref_distance=8, gain_db=-2)
    lights(cube, on=[(on, off)])

    # once: a ball drops and bounces, a beep at each contact
    b = o + Vector((40, 0, 0))
    cams["once"] = camera("sources_once_cam", b + Vector((0, 0, EYE)), b + Vector((0, 6, 0.9)))
    mesh(bpy.ops.mesh.primitive_cylinder_add, "sources_floor", b + Vector((0, 6, 0.05)), "grey", radius=1.2, depth=0.1)
    ball = mesh(bpy.ops.mesh.primitive_uv_sphere_add, "sources_ball", b + Vector((0, 6, 2.4)), "cyan", glow=True,
                radius=0.3)
    contacts = bounce(ball, b + Vector((0, 6, 0.4)), w["once"], release_s=0.6, height=2.0, until_s=4.6)
    segments(ball, "location", ball_runs.pop(ball.name))
    tag.add_sound(ball, "beep.wav", id=ID("sources", "once", "ball"), mode="once", frame=contacts, ref_distance=6)
    lights(ball, flashes=contacts)

    # pitch: three cubes play the same 1 kHz loop at pitch 0.5, 1 and 2
    c = o + Vector((80, 0, 0))
    cams["pitch"] = camera("sources_pitch_cam", c + Vector((0, 0, EYE)), c + Vector((0, 10, 1.0)))
    for i, (pitch, size, x) in enumerate([(0.5, 1.6, -3.2), (1.0, 1.0, 0.0), (2.0, 0.6, 3.2)]):
        obj = mesh(bpy.ops.mesh.primitive_cube_add, f"sources_pitch{i}", c + Vector((x, 10, size / 2)), "purple",
                   glow=True, size=size)
        text(f"sources_pitch{i}_text", f"pitch {pitch:g}", c + Vector((x, 10, 2.3)), 0.4, rotation=(math.pi / 2, 0, 0))
        a0, a1 = w["pitch"].at(0.6 + 1.5 * i), w["pitch"].at(1.8 + 1.5 * i)
        tag.add_sound(obj, "sine_1k.wav", id=ID("sources", "pitch", f"cube{i}"), frame=a0, end_frame=a1, pitch=pitch,
                      ref_distance=10, gain_db=-8, loop_phase=0.0)
        lights(obj, on=[(a0, a1)])

    # bed: an ambience bed and a ticking sphere; the camera pans 60° to the left
    d = o + Vector((120, 0, 0))
    cam = cams["bed"] = camera("sources_bed_cam", d + Vector((0, 0, EYE)), d + Vector((0, 8, EYE)))
    sphere = mesh(bpy.ops.mesh.primitive_uv_sphere_add, "sources_tick", d + Vector((0, 8, EYE)), "green", glow=True,
                  radius=0.35)
    ticks = [w["bed"].at(0.6 + 0.5 * i) for i in range(12)]
    tag.add_sound(sphere, "white_burst.wav", id=ID("sources", "bed", "tick"), mode="once", frame=ticks, ref_distance=8,
                  gain_db=-4)
    lights(sphere, flashes=ticks, decay_s=0.15)
    bed = empty("sources_bed", d)
    tag.add_sound(bed, "ambience_stereo.wav", id=ID("sources", "bed", "ambience"), spatial=False,
                  frame=w["bed"].at(0.3), end_frame=w["bed"].at(6.5), fade_in=0.5, fade_out=0.4, gain_db=4)
    rot = cam.rotation_euler.copy()
    turned = rot.copy()
    turned.z += math.radians(60)
    segments(cam, "rotation_euler", [[(t.title.first, rot)], [(w["bed"].at(2.0), rot), (w["bed"].at(4.5), turned)]])
    return cams


def ch_distance(t, o):
    w = t.passes
    cam = camera("distance_cam", o + Vector((0, 0, EYE)), o + Vector((-2, 20, EYE)), lens=28)
    posts = [2, 4, 8, 16, 32, 64]
    x = 0.6
    for i, d in enumerate(posts):  # fanned out to the left, labels at eye level so they do not overlap
        a = math.radians(-28 + 5.0 * i)
        at = o + Vector((d * math.sin(a), d * math.cos(a), 0))
        mesh(bpy.ops.mesh.primitive_cylinder_add, f"distance_post{d}", at + Vector((0, 0, EYE / 2)), "grey",
             radius=0.006 * d + 0.02, depth=EYE)
        text(f"distance_post{d}_text", f"{d} m", at + Vector((0, 0, EYE + 0.04 * d)), 0.03 * d,
             rotation=(math.pi / 2, 0, -a))  # facing the camera
    sphere = mesh(bpy.ops.mesh.primitive_uv_sphere_add, "distance_sphere", o + Vector((x, math.sqrt(4 - x * x), EYE)),
                  "red", glow=True, radius=0.3)
    runs, lit = [], []
    for p, model in (("off", "none"), ("on", "inverse_clamped")):
        win = w[p]
        run, s = [(win.first, o + Vector((x, math.sqrt(4 - x * x), EYE)))], 0.5
        for i, d in enumerate(posts):
            pos = o + Vector((x, math.sqrt(d * d - x * x), EYE))
            if i:
                s += 0.35
            run.append((win.at(s), pos))
            s += 1.0
            run.append((win.at(s), pos))
        runs.append(run)
        on, off = win.at(0.4), win.at(8.2)
        tag.add_sound(sphere, "noise_pink.wav", id=ID("distance", p, "sphere"), frame=on, end_frame=off,
                      distance_model=model, ref_distance=2, doppler=0.0, air_absorption=0.0, gain_db=-6, fade_out=0.2,
                      loop_phase=0.0)
        lit.append((on, off))
    lights(sphere, on=lit)
    segments(sphere, "location", runs)
    return {"off": cam, "on": cam}


def ch_panning(t, o):
    w = t.passes["amplitude"]
    cam = camera("panning_cam", o + Vector((0, 0, EYE)), o + Vector((0, 6, EYE)), lens=18)
    sphere = mesh(bpy.ops.mesh.primitive_uv_sphere_add, "panning_sphere", o + Vector((0, 6, EYE)), "blue", glow=True,
                  radius=0.35)

    def at(f):
        a = math.radians(40) * math.sin(2 * math.pi * ((f - w.first) / FPS - 0.75) / 5.0)
        return o + Vector((6 * math.sin(a), 6 * math.cos(a), EYE))

    segments(sphere, "location", [sampled(at, w.at(0.75), w.at(5.75))])
    on, off = w.at(0.5), w.at(6.3)
    tag.add_sound(sphere, "noise_pink.wav", id=ID("panning", "amplitude", "sphere"), frame=on, end_frame=off,
                  ref_distance=6, gain_db=-6)
    lights(sphere, on=[(on, off)])
    for i in range(-4, 5):  # posts on the arc, for orientation
        a = math.radians(10 * i)
        mesh(bpy.ops.mesh.primitive_cylinder_add, f"panning_post{i}", o + Vector((7.5 * math.sin(a), 7.5 * math.cos(a), 0.4)),
             "grey", radius=0.04, depth=0.8)
    return {"amplitude": cam}


def ch_screen(t, o):
    w = t.passes
    cam = camera("screen_cam", o + Vector((0, 0, EYE)), o + Vector((0, 20, EYE)), lens=24)
    hud = huds[cam.name]
    runs, hud_runs = [], []
    for p in ("camera", "screen"):
        a, b = w[p].at(1.0), w[p].at(5.0)
        runs.append([(w[p].first, 24.0), (a, 24.0), (b, 105.0)])
        hud_runs.append([(w[p].first, Vector((0, 0, -24 / 50))), (a, Vector((0, 0, -24 / 50))),
                         (b, Vector((0, 0, -105 / 50)))])
    segments(cam.data, "lens", runs)
    segments(hud, "location", hud_runs)
    for side, color, name in ((-1, "orange", "left"), (1, "green", "right")):
        a = math.radians(8.5) * side  # near the frame edges at 105 mm (half angle 9.7°)
        obj = mesh(bpy.ops.mesh.primitive_cube_add if side < 0 else bpy.ops.mesh.primitive_uv_sphere_add,
                   f"screen_{name}", o + Vector((20 * math.sin(a), 20 * math.cos(a), EYE)), color, glow=True,
                   **({"size": 0.8} if side < 0 else {"radius": 0.45}))
        flashes = []
        for p in ("camera", "screen"):
            f = [w[p].at(0.6 + 1.0 * i + (0.5 if side > 0 else 0.0)) for i in range(6)]
            tag.add_sound(obj, "white_burst.wav", id=ID("screen", p, name), mode="once", frame=f, ref_distance=20,
                          gain_db=-3)
            flashes += f
        lights(obj, flashes=flashes, decay_s=0.2)
    return {"camera": cam, "screen": cam}


def ch_delay(t, o):
    w = t.passes
    cam = camera("delay_cam", o + Vector((0, 0, 3)), o + Vector((0, 150, 2)))
    _, k = radar(cam, 400, [(w[p].first, w[p].last) for p in w], fov_deg=2 * math.degrees(math.atan(18 / 35)))
    radar_root = bpy.data.objects[f"{cam.name}_radar"]
    pads = [(343 / 10, -15.0, 1.0, "yellow"), (343 / 2, 10.0, 3.0, "orange"), (343.0, -2.0, 6.0, "red")]
    for i, (d, bearing, size, color) in enumerate(pads):
        z = size / 2
        h = math.sqrt(d * d - (3 - z) ** 2)
        a = math.radians(bearing)
        ground_pos = o + Vector((h * math.sin(a), h * math.cos(a), 0))
        pad = mesh(bpy.ops.mesh.primitive_cylinder_add, f"delay_pad{i}", ground_pos + Vector((0, 0, 0.05)), color,
                   glow=True, radius=size * 1.2, depth=0.1)
        block = mesh(bpy.ops.mesh.primitive_cube_add, f"delay_block{i}", ground_pos + Vector((0, 0, z + 2 * size)),
                     "white", size=size)
        text(f"delay_text{i}", f"{d:.0f} m", ground_pos + Vector((0, 0, 3.4 * size)), 0.7 * size,
             rotation=(math.pi / 2, 0, 0))
        fall = math.sqrt(2 * 2 * size / 9.81)
        runs, flashes = [], []
        for p in ("physical", "synced"):
            hit = w[p].at(1.0 + 2.0 * i)
            top = ground_pos + Vector((0, 0, z + 2 * size))
            runs.append([(w[p].first, top)] + sampled(
                lambda f, hit=hit, top=top: top - Vector((0, 0, min(2 * size, 0.5 * 9.81 * max(0.0, (f - hit) / FPS + fall) ** 2))),
                hit - fall * FPS, hit))
            tag.add_sound(block, "impact.wav", id=ID("delay", p, f"block{i}"), mode="once", frame=hit,
                          distance_model="none", air_absorption=0.0, sync_to_picture=p == "synced", gain_db=-4)
            flashes.append(hit)
            if p == "physical":  # the wavefront on the radar reaches the centre when the sound does
                r = ring(f"delay_ring{i}", radar_root, (h * math.sin(a) * k, h * math.cos(a) * k, 0.0003), color)
                grow = (d + 25) / 343 * FPS
                segments(r, "scale", [[(sb.FRAME_START - 1, (0, 0, 0))],
                                      [(hit, (0, 0, 0)), (hit + grow, ((d + 25) * k,) * 3)],
                                      [(hit + grow + 1, (0, 0, 0))]])
        segments(block, "location", runs)
        lights(pad, flashes=flashes, decay_s=0.5)
        dot(f"delay_dot{i}", radar_root, (h * math.sin(a) * k, h * math.cos(a) * k, 0.0006), color,
            [(w[p].first, w[p].last) for p in w], radius=0.0028)
    return {"physical": cam, "synced": cam}


def ch_doppler(t, o):
    w = t.passes
    cam = camera("doppler_cam", o + Vector((0, 0, EYE)), o + Vector((0, 10, EYE)))
    sphere = mesh(bpy.ops.mesh.primitive_uv_sphere_add, "doppler_sphere", o + Vector((-100, 10, EYE)), "yellow",
                  glow=True, radius=0.5)
    v, runs, on = 34.3, [], []
    for i, (p, factor) in enumerate((("off", 0.0), ("on", 1.0), ("double", 2.0))):
        a = w[p].at(0.3)
        b = a + 200 / v * FPS
        x0 = -100 if i % 2 == 0 else 100  # back and forth: no jump between passes
        runs.append([(a, o + Vector((x0, 10, EYE))), (b, o + Vector((-x0, 10, EYE)))])
        # the fade-out ends with the motion: a stopped source would sound at 1000 Hz again
        tag.add_sound(sphere, "sine_1k.wav", id=ID("doppler", p, "sphere"), frame=a, end_frame=b - 0.3 * FPS,
                      fade_in=0.2, fade_out=0.3, doppler=factor, ref_distance=10, gain_db=-4, loop_phase=0.0)
        on.append((a, b))
    segments(sphere, "location", runs)
    lights(sphere, on=on)
    for x in range(-30, 31, 5):  # markers along the path
        mesh(bpy.ops.mesh.primitive_cylinder_add, f"doppler_marker{x}", o + Vector((x, 12, 0.3)), "grey", radius=0.05,
             depth=0.6)
    return {p: cam for p in w}


def ch_air(t, o):
    w = t.passes
    cam = camera("air_cam", o + Vector((0, 0, 2)), o + Vector((0, 300, 6)))
    for i, (d, bearing, color) in enumerate([(10, -18.0, "yellow"), (100, -6.0, "orange"), (300, 5.0, "red"),
                                             (600, 16.0, "purple")]):
        a = math.radians(bearing)
        height = 0.1 * d
        pillar = mesh(bpy.ops.mesh.primitive_cylinder_add, f"air_pillar{i}",
                      o + Vector((d * math.sin(a), d * math.cos(a), height / 2)), color, glow=True, radius=0.02 * d,
                      depth=height)
        text(f"air_text{i}", f"{d} m", o + Vector((d * math.sin(a), d * math.cos(a), height + 0.04 * d)), 0.035 * d,
             rotation=(math.pi / 2, 0, -a))  # facing the camera
        flashes = []
        for p, air in (("off", 0.0), ("on", 1.0)):
            f = w[p].at(0.5 + 1.2 * i)  # the last arrives (1.75 s later) within the pass
            tag.add_sound(pillar, "white_burst_long.wav", id=ID("air", p, f"pillar{i}"), mode="once", frame=f,
                          distance_model="none", sync_to_picture=True, air_absorption=air, gain_db=-8)
            flashes.append(f)
        lights(pillar, on=[(f, f + 0.75 * FPS) for f in flashes])
    return {p: cam for p in w}


def orbit_stage(key: str, t, o, sample: str, bursts: bool):
    """A source circles the camera clockwise at 5 m (front, right, behind, left); a radar shows it."""
    w = t.passes
    cam = camera(f"{key}_cam", o + Vector((0, 0, EYE)), o + Vector((0, 10, EYE)), lens=18)
    pivot = empty(f"{key}_pivot", o + Vector((0, 0, EYE)))
    sphere = mesh(bpy.ops.mesh.primitive_uv_sphere_add, f"{key}_sphere", (0, 0, 0), "cyan", glow=True, radius=0.35)
    sphere.parent = pivot
    sphere.location = (0, 5, 0)
    for i in range(8):  # posts on a circle, for orientation
        a = 2 * math.pi * i / 8
        mesh(bpy.ops.mesh.primitive_cylinder_add, f"{key}_post{i}", o + Vector((7 * math.sin(a), 7 * math.cos(a), 0.5)),
             "grey", radius=0.06, depth=1.0)
    windows = [(w[p].first, w[p].last) for p in w]
    radar_root, k = radar(cam, 8, windows, fov_deg=2 * math.degrees(math.atan(18 / 18)))
    dot_pivot = empty(f"{key}_radar_pivot", (0, 0, 0.0006), parent=radar_root)
    dot(f"{key}_radar_dot", dot_pivot, (0, 5 * k, 0), "cyan", windows)
    runs, on, flashes = [], [], []
    for p in w:
        a, b = w[p].at(0.25), w[p].at(6.25)
        runs.append([(w[p].first, (0, 0, 0)), (a, (0, 0, 0)), (b, (0, 0, -2 * math.pi))])
        if bursts:
            f = [a + i * 0.25 * FPS for i in range(25)]
            tag.add_sound(sphere, sample, id=ID(key, p, "sphere"), mode="once", frame=f, ref_distance=5, gain_db=-4)
            flashes += f
        else:
            tag.add_sound(sphere, sample, id=ID(key, p, "sphere"), frame=a, end_frame=b, ref_distance=5, gain_db=-6,
                          loop_phase=0.0)  # the same noise in every pass, for a direct comparison
            on.append((a, b))
    segments(pivot, "rotation_euler", runs)
    segments(dot_pivot, "rotation_euler", runs)
    lights(sphere, on=on, flashes=flashes, decay_s=0.15)
    return {p: cam for p in w}


def ch_ears(t, o):
    return orbit_stage("ears", t, o, "white_burst.wav", bursts=True)


def ch_rear(t, o):
    return orbit_stage("rear", t, o, "noise_pink.wav", bursts=False)


def ch_cone(t, o):
    w = t.passes
    cam = camera("cone_cam", o + Vector((0, 0, EYE)), o + Vector((0, 6, 1.2)))
    mesh(bpy.ops.mesh.primitive_cylinder_add, "cone_table", o + Vector((0, 6, 0.05)), "grey", radius=1.0, depth=0.1)
    mesh(bpy.ops.mesh.primitive_cylinder_add, "cone_stand", o + Vector((0, 6, 0.8)), "grey", radius=0.05, depth=1.5)
    pivot = empty("cone_pivot", o + Vector((0, 6, EYE)))
    horn = mesh(bpy.ops.mesh.primitive_cone_add, "cone_horn", (0, 0, 0), "orange", glow=True, radius1=0.45,
                radius2=0.08, depth=1.0)
    horn.parent = pivot
    horn.location = (0, 0, 0)
    horn.rotation_euler = (-math.pi / 2, 0, 0)  # the wide end (local -Z, the forward axis) faces the camera
    runs, on = [], []
    for p, cone in (("omni", {}), ("cone", {"cone_inner_deg": 60.0, "cone_outer_deg": 180.0, "cone_outer_gain_db": -24.0})):
        a, b = w[p].at(0.5), w[p].at(6.5)
        runs.append([(w[p].first, (0, 0, 0)), (a, (0, 0, 0)), (b, (0, 0, 2 * math.pi))])
        tag.add_sound(horn, "noise_pink.wav", id=ID("cone", p, "horn"), frame=w[p].at(0.3), end_frame=w[p].at(6.7),
                      ref_distance=6, gain_db=-6, forward_axis="-Z", **cone)
        on.append((w[p].at(0.3), w[p].at(6.7)))
    segments(pivot, "rotation_euler", runs)
    lights(horn, on=on)
    return {p: cam for p in w}


def ch_occlusion(t, o):
    w = t.passes
    cam = camera("occlusion_cam", o + Vector((0, 0, EYE)), o + Vector((0, 10, 1.4)))
    wall = mesh(bpy.ops.mesh.primitive_cube_add, "occlusion_wall", o + Vector((0, 8, 1.5)),
                material=surface("wall", (0.35, 0.55, 0.8), alpha=0.35), size=1)
    wall.scale = (6, 0.3, 3)
    occluders.add(wall.name)
    sphere = mesh(bpy.ops.mesh.primitive_uv_sphere_add, "occlusion_sphere", o + Vector((-9, 14, 1.2)), "red", glow=True,
                  radius=0.4)
    runs, on = [], []
    for p, occ in (("off", False), ("on", True)):
        a, b = w[p].at(0.5), w[p].at(6.5)
        runs.append([(w[p].first, o + Vector((-9, 14, 1.2))), (a, o + Vector((-9, 14, 1.2))),
                     (b, o + Vector((9, 14, 1.2)))])
        tag.add_sound(sphere, "noise_pink.wav", id=ID("occlusion", p, "sphere"), frame=w[p].at(0.3),
                      end_frame=w[p].at(7.0), ref_distance=14, gain_db=-4, occlusion=occ)
        on.append((w[p].at(0.3), w[p].at(7.0)))
    segments(sphere, "location", runs)
    lights(sphere, on=on)
    return {p: cam for p in w}


def ch_reverb(t, o):
    w = t.passes
    cam = camera("reverb_cam", o + Vector((0, 0, EYE)), o + Vector((0, 8, 1.0)))
    ball = mesh(bpy.ops.mesh.primitive_uv_sphere_add, "reverb_ball", o + Vector((0, 5, 2.4)), "orange", glow=True,
                radius=0.3)
    flashes = []
    for p in ("dry", "room", "alley", "hall"):
        floor = o + Vector((0, 5, 0.3))
        hits = bounce(ball, floor, w[p], release_s=0.4, height=2.0, until_s=2.4)
        tag.add_sound(ball, "impact.wav", id=ID("reverb", p, "ball"), mode="once", frame=hits, ref_distance=5, gain_db=-4)
        flashes += hits
    # far: the ball hops away from 3 m to 60 m, one hop every 0.6 s
    win = w["far"]
    hop, hops = 0.6, 10
    y = [3 + (60 - 3) * i / (hops - 1) for i in range(hops)]
    run = [(win.first, o + Vector((0, y[0], 0.3)))]
    for i in range(hops - 1):
        t0 = 0.5 + i * hop
        run += [(win.at(t0 + j / 8 * hop), o + Vector((0, y[i] + j / 8 * (y[i + 1] - y[i]), 0.3 + 3.6 * j / 8 * (1 - j / 8))))
                for j in range(8)]
    run.append((win.at(0.5 + (hops - 1) * hop), o + Vector((0, y[-1], 0.3))))
    hits = [win.at(0.5 + i * hop) for i in range(hops)]
    ball_runs[ball.name].append(run)
    segments(ball, "location", ball_runs.pop(ball.name))
    tag.add_sound(ball, "impact.wav", id=ID("reverb", "far", "ball"), mode="once", frame=hits, ref_distance=5, gain_db=-4)
    flashes += hits
    lights(ball, flashes=flashes, decay_s=0.25)
    for i in range(8):  # distance markers along the way
        mesh(bpy.ops.mesh.primitive_cylinder_add, f"reverb_post{i}", o + Vector((-1.5, 5 + 8 * i, 0.4)), "grey",
             radius=0.05, depth=0.8)
    return {p: cam for p in w}


def ch_cuts(t, o):
    w = t.passes["cuts"]
    a = camera("cuts_cam_a", o + Vector((0, -8, 1.8)), o + Vector((0, 0, 0.8)))
    b = camera("cuts_cam_b", o + Vector((-17, -17, 3.5)), o + Vector((0, 0, 1.0)), lens=50)
    cube = mesh(bpy.ops.mesh.primitive_cube_add, "cuts_cube", o + Vector((-4, 0, 0.6)), "green", glow=True, size=1.2)
    segments(cube, "location", [[(w.first, o + Vector((-4, 0, 0.6))), (w.at(0.5), o + Vector((-4, 0, 0.6))),
                                 (w.at(8.0), o + Vector((4, 0, 0.6)))]])
    on, off = w.at(0.3), w.at(8.2)
    tag.add_sound(cube, "engine_hum.wav", id=ID("cuts", "cuts", "cube"), frame=on, end_frame=off, ref_distance=5,
                  gain_db=-2)
    lights(cube, on=[(on, off)])
    for i in range(-3, 4):
        mesh(bpy.ops.mesh.primitive_cylinder_add, f"cuts_post{i}", o + Vector((2 * i, 1.5, 0.3)), "grey", radius=0.05,
             depth=0.6)
    for s, cam in ((2.0, b), (4.0, a), (6.0, b)):
        switches.append((w.at(s), cam))
    return {"cuts": [a, b]}


def ch_phase(t, o):
    w = t.passes
    cam = camera("phase_cam", o + Vector((0, 0, EYE)), o + Vector((0, 12, 0.8)))
    for i in range(8):
        x = -5.25 + 1.5 * i
        cube = mesh(bpy.ops.mesh.primitive_cube_add, f"phase_cube{i}", o + Vector((x, 12, 0.5)), "blue", glow=True,
                    size=1.0)
        on = []
        for p, phase in (("zero", 0.0), ("random", "random")):
            a, b = w[p].at(0.4), w[p].at(5.0)
            tag.add_sound(cube, "engine_hum.wav", id=ID("phase", p, f"cube{i}"), frame=a, end_frame=b, loop_phase=phase,
                          ref_distance=12, gain_db=-18)
            on.append((a, b))
        lights(cube, on=on)
    return {p: cam for p in w}


def ch_together(t, o):
    w = t.passes["all"]
    cam = camera("together_cam", o + Vector((0, 0, EYE)), o + Vector((0, 20, 2.5)), lens=20)
    segments(cam, "location", [[(t.title.first, cam.location.copy()), (w.last, cam.location + Vector((0, 3, 0)))]])
    wall = mesh(bpy.ops.mesh.primitive_cube_add, "together_wall", o + Vector((12, 12, 2)),
                material=surface("wall", (0.35, 0.55, 0.8), alpha=0.35), size=1)
    wall.scale = (16, 0.4, 4)
    occluders.add(wall.name)
    ship = mesh(bpy.ops.mesh.primitive_cone_add, "together_ship", o + Vector((-150, 25, 3)), "red", glow=True,
                radius1=1.2, depth=4)
    ship.rotation_euler = (0, math.pi / 2, 0)
    a, b = w.at(1.0), w.at(11.0)
    segments(ship, "location", [[(w.first, o + Vector((-150, 25, 3))), (a, o + Vector((-150, 25, 3))),
                                 (b, o + Vector((150, 25, 3)))]])
    tag.add_sound(ship, "engine_hum.wav", id=ID("together", "all", "ship"), frame=a, end_frame=b - 1.0 * FPS,
                  ref_distance=15, gain_db=-2, fade_in=1.0, fade_out=1.0)
    tag.add_sound(ship, "whoosh.wav", id=ID("together", "all", "whoosh"), mode="once", frame=w.at(6.0) - 0.8 * FPS,
                  ref_distance=15, gain_db=-4)
    lights(ship, on=[(a, b)])
    beacon = mesh(bpy.ops.mesh.primitive_uv_sphere_add, "together_beacon", o + Vector((-3, 9, 0.5)), "yellow",
                  glow=True, radius=0.5)
    beeps = [w.at(0.5 + i) for i in range(14)]
    tag.add_sound(beacon, "beep.wav", id=ID("together", "all", "beacon"), mode="once", frame=beeps, ref_distance=4,
                  gain_db=-10)
    lights(beacon, flashes=beeps, decay_s=0.3)
    ball = mesh(bpy.ops.mesh.primitive_uv_sphere_add, "together_ball", o + Vector((2.5, 8, 3)), "cyan", glow=True,
                radius=0.3)
    hits = bounce(ball, o + Vector((2.5, 8, 0.3)), w, release_s=1.5, height=2.5, until_s=4.5)
    segments(ball, "location", ball_runs.pop(ball.name))
    tag.add_sound(ball, "impact.wav", id=ID("together", "all", "ball"), mode="once", frame=hits, ref_distance=6,
                  gain_db=-4)
    lights(ball, flashes=hits)
    bed = empty("together_bed", o)
    tag.add_sound(bed, "ambience_stereo.wav", id=ID("together", "all", "ambience"), spatial=False, frame=w.at(0.0),
                  end_frame=w.at(14.5), fade_in=0.8, fade_out=0.5, gain_db=0)
    for i in range(6):
        mesh(bpy.ops.mesh.primitive_cube_add, f"together_house{i}", o + Vector((-30 + 12 * i, 45, 4)), "grey", size=8)
    return {"all": cam}


# --- driver --------------------------------------------------------------------------------------

def build(engine: str, resolution: tuple[int, int], percent: int, samples: int) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps, scene.render.fps_base = FPS, 1.0
    scene.frame_start, scene.frame_end = sb.FRAME_START, sb.frame_end()
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = percent
    scene.render.engine = engine
    if engine == "CYCLES":
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
    else:
        scene.eevee.taa_render_samples = samples
    try:
        scene.view_settings.view_transform = "Standard"
    except TypeError:
        pass
    world = bpy.data.worlds.new("World")
    world.color = (0.02, 0.025, 0.035)
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.02, 0.025, 0.035, 1)
    scene.world = world
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    scene.collection.objects.link(sun)

    tl = sb.timeline()
    intro_cam = None
    for index, (key_, timed) in enumerate(tl.items()):
        ch = timed.chapter
        if key_ == "outro":
            cam = intro_cam
            switches.append((timed.title.first, cam))
            title_card(cam, ch.title, ch.subtitle, (timed.title.first, timed.title.last), big=True)
            continue
        origin = stage(key_, index, size=1500.0 if key_ in ("delay", "air") else 300.0)
        made = globals()[f"ch_{key_}"](timed, origin)
        if key_ == "intro":
            intro_cam = made
            switches.append((timed.title.first, made))
            title_card(made, ch.title, ch.subtitle, (timed.title.first, timed.title.last), big=True)
            continue
        cams = {p: (c if isinstance(c, list) else [c]) for p, c in made.items()}
        first = cams[ch.passes[0].key][0]
        switches.append((timed.title.first, first))
        title_card(first, ch.title, ch.subtitle, (timed.title.first, timed.title.last))
        for p in ch.passes:
            win = timed.passes[p.key]
            switches.append((win.first, cams[p.key][0]))
            for cam in cams[p.key]:
                label(cam, ch.title, p.label, (win.first, win.last), f"{cam.name}_{p.key}")

    scene.timeline_markers.clear()
    for frame, cam in sorted(switches, key=lambda s: s[0]):
        m = scene.timeline_markers.new(f"{cam.name}@{round(frame)}", frame=round(frame))
        m.camera = cam
    scene.camera = switches[0][1]
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.name not in occluders:
            obj["sfx_occluder"] = False
    tag.set_scene_settings(scene, samples_root=str(REPO / "samples") + "/", cull_db=None, detail_voices=None)
    scene.frame_set(sb.FRAME_START)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--save", default="out/showcase/showcase.blend")
    p.add_argument("--engine", choices=("CYCLES", "BLENDER_EEVEE"), default="CYCLES")
    p.add_argument("--resolution", default=f"{sb.RESOLUTION[0]}x{sb.RESOLUTION[1]}")
    p.add_argument("--percent", type=int, default=100)
    p.add_argument("--samples", type=int, default=64)
    args = p.parse_args(argv)
    build(args.engine, tuple(int(v) for v in args.resolution.split("x")), args.percent, args.samples)
    path = Path(args.save).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    print(f"saved {path}")
