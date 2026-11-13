"""Overlays: title page, lower third, section tag, code panel, fades, cards (in Blender).

Everything is an emissive mesh parented to a camera's overlay root (``base.hud_of``), where the
frame is 0.72 x 0.405 m, so the farm renders the final picture (P4). Text is converted to meshes
at build time (C7). Positions follow sections/README.md: x in fractions of the width from the
left, baselines and cap heights in fractions of the height from the top. Every text is measured
and the build stops if one is wider than its place: text is never scaled or cut to fit.
"""

from __future__ import annotations

import math
from pathlib import Path

import bpy

from . import base
from .base import HUD_H, HUD_W, key

FONT_DIR = Path(bpy.utils.system_resource("DATAFILES", path="fonts"))
BOLD = 0.016
"""Outline offset that makes the regular face bold, as a fraction of the font size. Above about 0.02
Blender's offset closes small counters (the crossbar of "A" disappears)."""

_fonts: dict[str, object] = {}
_caps: dict[str, float] = {}


class TextTooWide(Exception):
    pass


def font(kind: str):
    """``sans`` (Inter, Blender's UI font) or ``mono`` (DejaVu Sans Mono), both shipped with Blender."""
    if kind not in _fonts:
        _fonts[kind] = bpy.data.fonts.load(str(FONT_DIR / {"sans": "Inter.woff2", "mono": "DejaVuSansMono.woff2"}[kind]))
    return _fonts[kind]


def hx(f: float) -> float:
    """HUD x of a fraction of the width from the left."""
    return -HUD_W / 2 + f * HUD_W


def hy(f: float) -> float:
    """HUD y of a fraction of the height from the top."""
    return HUD_H / 2 - f * HUD_H


def _curve(body: str, kind: str, size: float, bold: bool, spacing: float):
    cu = bpy.data.curves.new("text", "FONT")
    cu.body = body
    cu.font = font(kind)
    cu.size = size
    cu.offset = BOLD * size if bold else 0.0
    cu.space_character = spacing
    cu.align_x = "LEFT"
    return cu


def _to_mesh(cu, name: str):
    tmp = bpy.data.objects.new("tmp", cu)
    bpy.context.scene.collection.objects.link(tmp)
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(tmp)
    bpy.data.curves.remove(cu)
    me.name = name
    return me


def _cap_ratio(kind: str) -> float:
    """Cap height of the font at size 1."""
    if kind not in _caps:
        me = _to_mesh(_curve("H", kind, 1.0, False, 1.0), "cap")
        _caps[kind] = max(v.co.y for v in me.vertices) - min(v.co.y for v in me.vertices)
        bpy.data.meshes.remove(me)
    return _caps[kind]


def text_width(body: str, cap: float, kind: str = "sans", bold: bool = False, spacing: float = 1.0) -> float:
    """Width of a text as a fraction of the frame width, at a cap height in fractions of the height."""
    size = cap * HUD_H / _cap_ratio(kind)
    me = _to_mesh(_curve(body, kind, size, bold, spacing), "measure")
    xs = [v.co.x for v in me.vertices] or [0.0]
    bpy.data.meshes.remove(me)
    return (max(xs) - min(xs)) / HUD_W


def text(parent, name: str, body: str, cap: float, x: float, baseline: float, material, kind: str = "sans",
         bold: bool = False, align: str = "LEFT", spacing: float = 1.0, max_width: float | None = None, z: float = 0.002):
    """A text mesh on the overlay root. Returns (object, width as a fraction of the frame width)."""
    size = cap * HUD_H / _cap_ratio(kind)
    me = _to_mesh(_curve(body, kind, size, bold, spacing), name)
    xs = [v.co.x for v in me.vertices] or [0.0]
    x0, x1 = min(xs), max(xs)
    width = (x1 - x0) / HUD_W
    if max_width is not None and width > max_width + 1e-6:
        raise TextTooWide(f"{name}: {body!r} is {width:.3f} of the frame wide, its place {max_width:.3f}")
    shift = {"LEFT": -x0, "CENTER": -(x0 + x1) / 2, "RIGHT": -x1}[align]
    for v in me.vertices:
        v.co.x += shift
    me.materials.append(material)
    obj = base.link(bpy.data.objects.new(name, me))
    obj.parent = parent
    obj.location = (hx(x), hy(baseline), z)
    _overlay_visibility(obj)
    return obj, width


def world_text(name: str, body: str, location, cap_m: float, material, rotation, kind: str = "mono",
               bold: bool = False, plate=None):
    """A text mesh standing in the scene, centred on ``location`` (its baseline), cap height in metres;
    with ``plate`` (a material) on a dark plate of its own size behind it."""
    size = cap_m / _cap_ratio(kind)
    me = _to_mesh(_curve(body, kind, size, bold, 1.0), name)
    xs = [v.co.x for v in me.vertices] or [0.0]
    half = (max(xs) - min(xs)) / 2
    for v in me.vertices:
        v.co.x -= (min(xs) + max(xs)) / 2
    me.materials.append(material)
    obj = base.link(bpy.data.objects.new(name, me))
    obj.location = tuple(location)
    obj.rotation_euler = rotation
    _overlay_visibility(obj)
    if plate is not None:
        pad = 0.35 * cap_m
        verts = [(-half - pad, -pad, -0.01), (half + pad, -pad, -0.01), (half + pad, cap_m + pad, -0.01),
                 (-half - pad, cap_m + pad, -0.01)]
        back = base.mesh_object(f"{name}.plate", verts, [(0, 1, 2, 3)], plate, obj)
        _overlay_visibility(back)
    return obj


def world_ring(name: str, centre, radius: float, width: float, material, facing=None, flat: bool = False,
               segments: int = 48):
    """A ring in the scene (metres): upright and turned towards ``facing`` (an (x, y) point), or
    lying flat on the ground."""
    verts, faces = [], []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        for r in (radius, radius - width):
            verts.append((r * math.cos(a), 0.0, r * math.sin(a)) if not flat else (r * math.cos(a), r * math.sin(a), 0.0))
    for i in range(segments):
        j = (i + 1) % segments
        faces.append((2 * i, 2 * j, 2 * j + 1, 2 * i + 1))
    obj = base.mesh_object(name, verts, faces, material, None, centre)
    if facing is not None:
        obj.rotation_euler = (0, 0, math.atan2(facing[0] - centre[0], -(facing[1] - centre[1])) + math.pi)
    _overlay_visibility(obj)
    return obj


def wrap(body: str, cap: float, width: float, kind: str = "sans", first_indent: float = 0.0, lines: int = 2) -> list[str]:
    """Wrap by measured width; the first line starts ``first_indent`` in. Two lines are balanced
    (the break that makes the longer line shortest). Stops the build if more than ``lines`` lines
    are needed."""
    words = body.split()
    if text_width(body, cap, kind) + first_indent <= width:
        return [body]
    if lines == 2:
        best = None
        for i in range(1, len(words)):
            a, b = " ".join(words[:i]), " ".join(words[i:])
            wa, wb = text_width(a, cap, kind) + first_indent, text_width(b, cap, kind)
            if wa <= width and wb <= width and (best is None or max(wa, wb) < best[0]):
                best = (max(wa, wb), [a, b])
        if best:
            return best[1]
    out, cur = [], ""
    for word in body.split():
        trial = f"{cur} {word}".strip()
        room = width - (first_indent if not out else 0.0)
        if cur and text_width(trial, cap, kind) > room:
            out.append(cur)
            cur = word
        else:
            cur = trial
    out.append(cur)
    if len(out) > lines:
        raise TextTooWide(f"{body!r} needs {len(out)} lines, at most {lines}")
    return out


def _overlay_visibility(obj) -> None:
    """Overlays are seen by the camera only: no light, no shadow, no reflection; no occlusion."""
    for attr in ("visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter", "visible_shadow"):
        setattr(obj, attr, False)
    obj["sfx_occluder"] = False


def rect(parent, name: str, x0: float, top: float, x1: float, bottom: float, material, z: float = 0.0):
    """A rectangle between fractions of the frame (x from the left, y from the top)."""
    verts = [(hx(x0), hy(bottom), 0), (hx(x1), hy(bottom), 0), (hx(x1), hy(top), 0), (hx(x0), hy(top), 0)]
    obj = base.mesh_object(name, verts, [(0, 1, 2, 3)], material, parent, (0, 0, z))
    _overlay_visibility(obj)
    return obj


def rounded(parent, name: str, x0: float, top: float, x1: float, bottom: float, radius: float, material,
            z: float = 0.0, segments: int = 6):
    """A rectangle with rounded corners (radius as a fraction of the height)."""
    r = radius * HUD_H
    ax0, ax1, ay0, ay1 = hx(x0), hx(x1), hy(bottom), hy(top)
    verts = []
    for cx, cy, a0 in ((ax1 - r, ay1 - r, 0), (ax0 + r, ay1 - r, 90), (ax0 + r, ay0 + r, 180), (ax1 - r, ay0 + r, 270)):
        for i in range(segments + 1):
            a = math.radians(a0 + 90 * i / segments)
            verts.append((cx + r * math.cos(a), cy + r * math.sin(a), 0))
    obj = base.mesh_object(name, verts, [tuple(range(len(verts)))], material, parent, (0, 0, z))
    _overlay_visibility(obj)
    return obj


def disc(parent, name: str, x: float, y: float, radius: float, material, hole: float = 0.0, z: float = 0.003,
         segments: int = 32):
    """A filled circle, or a ring when ``hole`` > 0 (radii as fractions of the height)."""
    cx, cy, r = hx(x), hy(y), radius * HUD_H
    outer = [(cx + r * math.cos(2 * math.pi * i / segments), cy + r * math.sin(2 * math.pi * i / segments), 0)
             for i in range(segments)]
    if hole <= 0:
        obj = base.mesh_object(name, outer, [tuple(range(segments))], material, parent, (0, 0, z))
    else:
        h = hole * HUD_H
        inner = [(cx + h * math.cos(2 * math.pi * i / segments), cy + h * math.sin(2 * math.pi * i / segments), 0)
                 for i in range(segments)]
        faces = [(i, (i + 1) % segments, segments + (i + 1) % segments, segments + i) for i in range(segments)]
        obj = base.mesh_object(name, outer + inner, faces, material, parent, (0, 0, z))
    _overlay_visibility(obj)
    return obj


class Layer:
    """Overlay materials that share one opacity curve: a title page, a label, a card."""

    def __init__(self, name: str):
        self.name = name
        self.materials: dict[str, object] = {}
        self.scrims: list = []

    def mat(self, colour_name: str, alpha: float = 1.0, strength: float = 1.0):
        k = f"{colour_name}|{alpha}"
        if k not in self.materials:
            mat = bpy.data.materials.new(f"{self.name}.{colour_name}")
            nt = mat.node_tree
            nt.nodes.remove(nt.nodes["Principled BSDF"])
            out = nt.nodes["Material Output"]
            em = nt.nodes.new("ShaderNodeEmission")
            em.inputs["Color"].default_value = base.colour(colour_name)
            em.inputs["Strength"].default_value = strength
            tr = nt.nodes.new("ShaderNodeBsdfTransparent")
            mix = nt.nodes.new("ShaderNodeMixShader")
            mix.name = "opacity"
            mix.inputs["Fac"].default_value = alpha
            mix["alpha"] = alpha
            nt.links.new(tr.outputs[0], mix.inputs[1])
            nt.links.new(em.outputs[0], mix.inputs[2])
            nt.links.new(mix.outputs[0], out.inputs["Surface"])
            mat.surface_render_method = "BLENDED"
            self.materials[k] = mat
        return self.materials[k]

    def scrim(self, colour_name: str, alpha: float, fade_from: float, fade_to: float):
        """Material whose opacity rises from 0 at ``fade_from`` to ``alpha`` at ``fade_to`` (fractions
        of the height from the top, applied over the object's own vertical extent via generated
        coordinates)."""
        mat = bpy.data.materials.new(f"{self.name}.scrim")
        nt = mat.node_tree
        nt.nodes.remove(nt.nodes["Principled BSDF"])
        out = nt.nodes["Material Output"]
        coords = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        ramp = nt.nodes.new("ShaderNodeMapRange")
        ramp.inputs["From Min"].default_value = 1.0
        ramp.inputs["From Max"].default_value = 0.0
        power = nt.nodes.new("ShaderNodeMath")
        power.operation = "POWER"
        power.inputs[1].default_value = 1.4
        gain = nt.nodes.new("ShaderNodeMath")
        gain.operation = "MULTIPLY"
        gain.name = "opacity_gain"
        gain.inputs[1].default_value = alpha
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = base.colour(colour_name)
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(coords.outputs["Generated"], sep.inputs[0])
        nt.links.new(sep.outputs["Y"], ramp.inputs["Value"])
        nt.links.new(ramp.outputs["Result"], power.inputs[0])
        nt.links.new(power.outputs[0], gain.inputs[0])
        nt.links.new(gain.outputs[0], mix.inputs["Fac"])
        nt.links.new(tr.outputs[0], mix.inputs[1])
        nt.links.new(em.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
        mat.surface_render_method = "BLENDED"
        mat["alpha"] = alpha
        self.scrims.append(mat)
        return mat

    def opacity(self, keys: list[tuple[float, float]]) -> None:
        """Key the layer's opacity (0 to 1, times each material's own alpha) at frames."""
        for mat in self.materials.values():
            sock = mat.node_tree.nodes["opacity"].inputs["Fac"]
            for frame, value in keys:
                key(sock, "default_value", frame, value * mat.node_tree.nodes["opacity"]["alpha"])
        for mat in self.scrims:
            sock = mat.node_tree.nodes["opacity_gain"].inputs[1]
            for frame, value in keys:
                key(sock, "default_value", frame, value * mat["alpha"])


def show(objs, windows) -> None:
    for o in objs:
        base.visible(o, windows, recursive=False)


# --- elements ------------------------------------------------------------------------------------

def dots(parent, name: str, layer: Layer, n: int, current: int, baseline: float, right: float = 0.95,
         objs: list | None = None) -> float:
    """One dot per pass, the current one filled (-1: none), right-aligned at ``right``; returns the
    left edge of the row."""
    r, gap = 0.0085, 0.0315 * HUD_H / HUD_W  # radius in heights, spacing in widths
    cy = baseline - r
    x_last = right - r * HUD_H / HUD_W
    for i in range(n):
        x = x_last - (n - 1 - i) * gap
        on = i == current
        d = disc(parent, f"{name}.dot{i}", x, cy, r, layer.mat("accent" if on else "muted"), hole=0.0 if on else 0.0055)
        if objs is not None:
            objs.append(d)
    return x_last - (n - 1) * gap - r * HUD_H / HUD_W


def headphones(parent, name: str, layer: Layer, x_right: float, baseline: float, objs: list) -> float:
    """A headphones mark ending at ``x_right``; returns its left edge."""
    h = 0.03
    w = h * HUD_H / HUD_W
    cx = x_right - w / 2
    seg = 16
    r_out, r_in = h / 2, h / 2 - 0.004
    cy = baseline - h * 0.55
    verts, faces = [], []
    for i in range(seg + 1):
        a = math.pi * i / seg
        verts += [(hx(cx) + r_out * HUD_H * math.cos(a), hy(cy) + r_out * HUD_H * math.sin(a), 0),
                  (hx(cx) + r_in * HUD_H * math.cos(a), hy(cy) + r_in * HUD_H * math.sin(a), 0)]
    for i in range(seg):
        faces.append((2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2))
    band = base.mesh_object(f"{name}.band", verts, faces, layer.mat("text"), parent, (0, 0, 0.003))
    _overlay_visibility(band)
    objs.append(band)
    for side in (-1, 1):
        x0 = cx + side * (r_out * HUD_H / HUD_W) - (0.0055 if side > 0 else 0.0)
        objs.append(rounded(parent, f"{name}.cup{side}", x0, cy - 0.002, x0 + 0.0055, baseline, 0.002,
                            layer.mat("text"), z=0.003))
    return x_right - w


def title_page(cam, section, window, n_passes: int) -> Layer:
    """The title page over the opening view (sections/README.md, "Title page"): fades from black is
    separate (``fade_black``); this dissolves in its last 12 frames."""
    tp = section.title_page
    hud = base.hud_of(cam)
    layer = Layer(f"{section.key}.title")
    objs = [rect(hud, f"{section.key}.title.card", -0.05, -0.05, 1.05, 1.05, layer.mat("bg", 0.82), z=0.0)]
    left, right = 0.10, 0.95
    objs.append(text(hud, f"{section.key}.title.kicker", "SOUNDSTAGE", 0.022, left, 0.36, layer.mat("accent"),
                     bold=True, spacing=1.9)[0])
    objs.append(text(hud, f"{section.key}.title.title", tp.title, 0.085, left, 0.50, layer.mat("text"), bold=True,
                     max_width=right - left)[0])
    objs.append(rect(hud, f"{section.key}.title.rule", left, 0.54 - 0.0028, left + 0.06, 0.54 + 0.0028,
                     layer.mat("accent"), z=0.002))
    for i, line in enumerate(wrap(tp.claim, 0.032, right - left)):
        objs.append(text(hud, f"{section.key}.title.claim{i}", line, 0.032, left, 0.61 + 0.055 * i, layer.mat("text"))[0])
    cap = 0.026
    chip, w = text(hud, f"{section.key}.title.code", tp.code, cap, left + 0.012, 0.74, layer.mat("code"), kind="mono",
                   max_width=right - left - 0.024, z=0.003)
    objs.append(chip)
    objs.append(rounded(hud, f"{section.key}.title.chip", left, 0.74 - cap - 0.017, left + w + 0.024, 0.74 + 0.017,
                        0.008, layer.mat("panel", 0.95), z=0.0015))
    dots_left = dots(hud, f"{section.key}.title", layer, n_passes, -1, 0.90, right, objs)
    if tp.headphones:
        dots_left = headphones(hud, f"{section.key}.title.phones", layer, dots_left - 0.02, 0.90, objs)
    label = "Listen for"
    lw = text_width(label, 0.024, bold=True) + 0.012
    lines = wrap(tp.listen, 0.024, dots_left - 0.03 - left, first_indent=lw)
    y0 = 0.90 - 0.045 * (len(lines) - 1)
    objs.append(text(hud, f"{section.key}.title.listen", label, 0.024, left, y0, layer.mat("accent"), bold=True)[0])
    for i, line in enumerate(lines):
        objs.append(text(hud, f"{section.key}.title.listen{i}", line, 0.024, left + (lw if i == 0 else 0), y0 + 0.045 * i,
                         layer.mat("text"))[0])
    show(objs, [(window.first, window.last)])
    layer.opacity([(window.last - 11, 1.0), (window.last + 1, 0.0)])
    return layer


def section_tag(cam, name: str, title: str, windows) -> None:
    hud = base.hud_of(cam)
    layer = Layer(f"{name}.tag")
    cap = 0.02
    w = text_width(title, cap, bold=True)
    objs = [text(hud, f"{name}.tag.text", title, cap, 0.05 + 0.009, 0.05 + 0.028, layer.mat("text"), bold=True)[0],
            rounded(hud, f"{name}.tag.chip", 0.05, 0.05, 0.05 + w + 0.018, 0.05 + 0.045, 0.008,
                    layer.mat("panel", 0.86), z=0.0015)]
    show(objs, windows)


def lower_third(cam, name: str, p, index: int, n: int, window) -> Layer:
    """State chip, label, setting and pass dots (sections/README.md, "Passes, labels and instruments")."""
    hud = base.hud_of(cam)
    layer = Layer(f"{name}.lower")
    objs = [rect(hud, f"{name}.lower.scrim", -0.05, 0.70, 1.05, 1.05, layer.scrim("bg", 0.9, 0.70, 1.0), z=0.0)]
    dots_left = dots(hud, f"{name}.lower", layer, n, index, 0.95, 0.95, objs)
    x = 0.05
    if p.chip:
        cap = 0.022
        w = text_width(p.chip, cap, bold=True)
        objs.append(text(hud, f"{name}.lower.chip_text", p.chip, cap, x + 0.01, 0.895, layer.mat("panel"), bold=True,
                         z=0.003)[0])
        objs.append(rounded(hud, f"{name}.lower.chip", x, 0.895 - cap - 0.014, x + w + 0.02, 0.895 + 0.016, 0.008,
                            layer.mat("accent" if p.chip == "WITH" else "muted"), z=0.0015))
        x += w + 0.02 + 0.015
    room = dots_left - 0.02 - x
    objs.append(text(hud, f"{name}.lower.label", p.label, 0.032, x, 0.90, layer.mat("text"), bold=True, max_width=room)[0])
    if p.setting:
        objs.append(text(hud, f"{name}.lower.setting", p.setting, 0.022, x, 0.95, layer.mat("code"), kind="mono",
                         max_width=room)[0])
    show(objs, [(window.first, window.last)])
    return layer


def fade_black(cam, name: str, frames_in: tuple[int, int] | None, frames_out: tuple[int, int] | None,
               window: tuple[int, int]) -> None:
    """A black plane in front of everything: opaque at ``frames_in[0]``, clear at ``frames_in[1]``;
    clear at ``frames_out[0]``, opaque at ``frames_out[1]``."""
    hud = base.hud_of(cam)
    layer = Layer(f"{name}.black")
    obj = rect(hud, f"{name}.black", -0.1, -0.1, 1.1, 1.1, layer.mat("black"), z=0.006)
    keys = [(window[0], 0.0)]
    if frames_in:
        keys = [(frames_in[0], 1.0), (frames_in[1], 0.0)]
    if frames_out:
        keys += [(frames_out[0], 0.0), (frames_out[1], 1.0)]
    layer.opacity(keys)
    show([obj], [window])


def centred_label(cam, name: str, body: str, window, cap: float = 0.04) -> Layer:
    """A large centred label in the lower third with its scrim (``intro``)."""
    hud = base.hud_of(cam)
    layer = Layer(f"{name}.label")
    objs = [rect(hud, f"{name}.label.scrim", -0.05, 0.70, 1.05, 1.05, layer.scrim("bg", 0.85, 0.70, 1.0), z=0.0),
            text(hud, f"{name}.label.text", body, cap, 0.5, 0.905, layer.mat("text"), bold=True, align="CENTER",
                 max_width=0.9)[0]]
    show(objs, [window])
    return layer


def wordmark_card(cam, name: str, tagline: str, note: str, window) -> Layer:
    """The wordmark page of ``intro``: card, wordmark, tagline, note, centred."""
    hud = base.hud_of(cam)
    layer = Layer(f"{name}.wordmark")
    objs = [rect(hud, f"{name}.wordmark.card", -0.05, -0.05, 1.05, 1.05, layer.mat("bg", 0.82), z=0.0),
            text(hud, f"{name}.wordmark.word", "soundstage", 0.09, 0.5, 0.49, layer.mat("text"), bold=True,
                 align="CENTER", max_width=0.9)[0],
            rect(hud, f"{name}.wordmark.rule", 0.47, 0.545 - 0.0028, 0.53, 0.545 + 0.0028, layer.mat("accent"), z=0.002),
            text(hud, f"{name}.wordmark.tagline", tagline, 0.032, 0.5, 0.62, layer.mat("text"), align="CENTER",
                 max_width=0.9)[0],
            text(hud, f"{name}.wordmark.note", note, 0.024, 0.5, 0.72, layer.mat("accent"), align="CENTER",
                 max_width=0.9)[0]]
    show(objs, [window])
    return layer


def code_panel(cam, name: str, lines: list[tuple[str, str]], window, top: float = 0.13) -> None:
    """Monospace lines on a dark panel at the upper left; each line is (text, colour name)."""
    hud = base.hud_of(cam)
    layer = Layer(f"{name}.code")
    cap, step, pad = 0.022, 0.042, 0.012
    objs, width = [], 0.0
    advance = (text_width("M" * 11, cap, "mono") - text_width("M", cap, "mono")) / 10  # one monospace cell
    for i, (body, colour_name) in enumerate(lines):
        indent = (len(body) - len(body.lstrip(" "))) * advance  # spaces have no glyph to measure
        obj, w = text(hud, f"{name}.code{i}", body.lstrip(" "), cap, 0.05 + pad + indent,
                      top + pad * 1.6 + cap + step * i, layer.mat(colour_name), kind="mono",
                      max_width=0.9 - 2 * pad - indent, z=0.003)
        objs.append(obj)
        width = max(width, w + indent)
    bottom = top + pad * 1.6 + cap + step * (len(lines) - 1) + pad * 1.6
    objs.append(rounded(hud, f"{name}.code.panel", 0.05, top, 0.05 + width + 2 * pad, bottom, 0.008,
                        layer.mat("panel", 0.86), z=0.0015))
    show(objs, [window])


def level_bars(cam, name: str, bars: list[tuple[str, list[tuple[float, float]]]], window, top: float = 0.06,
               floor_db: float = -40.0) -> None:
    """Horizontal level bars at the upper right, one per (label, [(frame, dB)]); keyed lengths."""
    hud = base.hud_of(cam)
    layer = Layer(f"{name}.bars")
    x0, length, step = 0.74, 0.18, 0.05
    objs = []
    panel_bottom = top + 0.025 + step * len(bars)
    objs.append(rounded(hud, f"{name}.bars.panel", x0 - 0.015, top, 0.95, panel_bottom, 0.008,
                        layer.mat("panel", 0.86), z=0.0015))
    for i, (label, curve) in enumerate(bars):
        y = top + 0.04 + step * i
        objs.append(text(hud, f"{name}.bars.label{i}", label, 0.02, x0, y, layer.mat("text"), max_width=0.08)[0])
        bx = x0 + 0.085
        bar_len = 0.95 - 0.012 - bx
        objs.append(rect(hud, f"{name}.bars.track{i}", bx, y - 0.02, bx + bar_len, y, layer.mat("muted", 0.35), z=0.002))
        bar = rect(hud, f"{name}.bars.bar{i}", 0.0, y - 0.02, 1.0, y, layer.mat("accent"), z=0.0025)
        # the bar mesh spans the whole width; its x scale and location give the keyed length
        objs.append(bar)
        for frame, level in curve:
            frac = min(max((level - floor_db) / -floor_db, 0.0), 1.0)
            key(bar, "scale", frame, (frac * bar_len, 1.0, 1.0))
            key(bar, "location", frame, (hx(bx) - hx(0.0) * frac * bar_len, 0.0, 0.0025))
    del length
    show(objs, [window])


def readout(cam, name: str, shots: list[tuple[str, tuple[int, int]]], cap: float = 0.045, right: float = 0.95,
            top: float = 0.05) -> None:
    """A large value at the upper right on a panel (a distance, a time): (text, frame window) pairs;
    a text that recurs is one object shown in each of its windows."""
    hud = base.hud_of(cam)
    layer = Layer(f"{name}.readout")
    pad = 0.014
    windows: dict[str, list] = {}
    for body, window in shots:
        windows.setdefault(body, []).append(window)
    widest = max(text_width(body, cap, bold=True) for body in windows)
    x0 = right - widest - 2 * pad * HUD_H / HUD_W
    panel = rounded(hud, f"{name}.readout.panel", x0, top, right, top + cap + 2.2 * pad, 0.008,
                    layer.mat("panel", 0.86), z=0.0015)
    for i, (body, wins) in enumerate(windows.items()):
        obj, _ = text(hud, f"{name}.readout{i}", body, cap, right - pad * HUD_H / HUD_W, top + 1.1 * pad + cap,
                      layer.mat("text"), bold=True, align="RIGHT", z=0.003)
        show([obj], wins)
    show([panel], [(min(w[0] for _, w in shots), max(w[1] for _, w in shots))])


def callout(cam, name: str, body: str, window: tuple[int, int], cap: float = 0.028, right: float = 0.95,
            top: float = 0.05, fade: int = 6) -> None:
    """A small chip at the upper right naming what is heard in plain words, with an accent bar on its
    left; it fades in and out over ``fade`` frames at the ends of its window (``finale``)."""
    hud = base.hud_of(cam)
    layer = Layer(f"{name}.callout")
    pad = 0.014
    w = text_width(body, cap, bold=True)
    x0 = right - w - 2 * pad * HUD_H / HUD_W - 0.006
    bottom = top + cap + 2.2 * pad
    objs = [text(hud, f"{name}.callout.text", body, cap, right - pad * HUD_H / HUD_W, top + 1.1 * pad + cap,
                 layer.mat("text"), bold=True, align="RIGHT", max_width=0.6, z=0.003)[0],
            rounded(hud, f"{name}.callout.chip", x0, top, right, bottom, 0.008, layer.mat("panel", 0.86), z=0.0015),
            rect(hud, f"{name}.callout.bar", x0, top + 0.012, x0 + 0.004, bottom - 0.012, layer.mat("accent"), z=0.002)]
    show(objs, [window])
    a, b = window
    layer.opacity([(a, 0.0), (a + fade, 1.0), (b - fade, 1.0), (b, 0.0)])


def gauge(cam, name: str, marks_db: list[float], needle: list[tuple[int, float]], window, top: float = 0.17,
          bottom: float = 0.62, right: float = 0.95, unit: str = "dB", signed: bool = False,
          highlights: tuple[float, ...] = ()) -> None:
    """A vertical scale at the right with labelled marks and a needle that jumps to each keyed value
    (constant between keys): the expected level at the camera, or a pitch keyed every frame.
    ``highlights`` are values marked in the accent colour on the scale (expected end points);
    ``signed`` writes a plus sign on positive labels."""
    hud = base.hud_of(cam)
    layer = Layer(f"{name}.gauge")
    hi, lo = max(marks_db), min(marks_db)
    cap = 0.02
    fmt = lambda v: (f"{v:+.0f}" if signed and v else f"{v:.0f}").replace("-", "−")  # noqa: E731  a real minus sign
    label_w = max(text_width(fmt(m), cap) for m in marks_db)
    scale_x = right - 0.012 - label_w - 0.012
    unit_w = text_width(unit, cap)
    left = min(scale_x - 0.05, right - unit_w - 0.024)
    head = 0.05 if left + 0.015 + unit_w < scale_x - 0.04 else 0.08  # a long unit gets a line of its own
    y_of = lambda v: top + head + (hi - v) / (hi - lo) * (bottom - top - head - 0.03)  # noqa: E731
    objs = [rounded(hud, f"{name}.gauge.panel", left, top, right + 0.005, bottom, 0.008,
                    layer.mat("panel", 0.86), z=0.0015),
            text(hud, f"{name}.gauge.unit", unit, cap, left + 0.015, top + 0.035, layer.mat("muted"))[0],
            rect(hud, f"{name}.gauge.axis", scale_x - 0.002, y_of(hi), scale_x + 0.0, y_of(lo), layer.mat("muted"),
                 z=0.002)]
    for i, m in enumerate(marks_db):
        y = y_of(m)
        objs.append(rect(hud, f"{name}.gauge.mark{i}", scale_x - 0.008, y - 0.002, scale_x, y + 0.002, layer.mat("muted"),
                         z=0.002))
        objs.append(text(hud, f"{name}.gauge.label{i}", fmt(m), cap, right - 0.006, y + cap / 2, layer.mat("text"),
                         align="RIGHT", z=0.003)[0])
    for i, v in enumerate(highlights):
        y = y_of(v)
        objs.append(rect(hud, f"{name}.gauge.highlight{i}", scale_x - 0.002, y - 0.0025, scale_x + 0.010, y + 0.0025,
                         layer.mat("accent"), z=0.0022))
    # the needle: a triangle pointing at the scale from the left, moved by its location
    x1, x0 = hx(scale_x - 0.010), hx(scale_x - 0.038)
    h = 0.016 * HUD_H
    tri = base.mesh_object(f"{name}.gauge.needle", [(x1, 0, 0), (x0, h, 0), (x0, -h, 0)], [(0, 1, 2)],
                           layer.mat("accent"), hud, (0, hy(y_of(needle[0][1])), 0.003))
    _overlay_visibility(tri)
    objs.append(tri)
    for frame, value in needle:
        key(tri, "location", frame, (0, hy(y_of(max(lo, min(hi, value)))), 0.003), "CONSTANT")
    show(objs, [window])


def band_strip(cam, name: str, bands: list[str], losses: list[tuple[int, list[float]]], window, top: float = 0.13,
               left: float = 0.05, max_db: float = 60.0, scale: tuple[float, ...] = (0, 20, 40, 60)) -> None:
    """Bars hanging from a zero line at the upper left, one per band, their length the expected loss
    in dB (clamped at ``max_db``); one set of keyed lengths per frame (constant between keys)."""
    hud = base.hud_of(cam)
    layer = Layer(f"{name}.bands")
    cap, col, gap, depth = 0.02, 0.028, 0.012, 0.16
    label_y = top + 0.04
    zero = label_y + 0.017
    x_bars = left + 0.05
    right = x_bars + len(bands) * (col + gap) - gap
    objs = [rounded(hud, f"{name}.bands.panel", left, top, right + 0.01, zero + depth + 0.03, 0.008,
                    layer.mat("panel", 0.86), z=0.0015),
            text(hud, f"{name}.bands.unit", "dB", cap, x_bars - 0.008, label_y, layer.mat("muted"), align="RIGHT",
                 z=0.003)[0]]
    for i, v in enumerate(scale):
        y = zero + depth * v / max_db
        if v:
            objs.append(text(hud, f"{name}.bands.scale{i}", f"−{v:.0f}", cap, x_bars - 0.008, y + cap / 2,
                             layer.mat("muted"), align="RIGHT", z=0.003)[0])
        objs.append(rect(hud, f"{name}.bands.grid{i}", x_bars - 0.004, y - 0.0012, right, y + 0.0012,
                         layer.mat("muted", 0.5), z=0.002))
    for i, label in enumerate(bands):
        x = x_bars + i * (col + gap)
        objs.append(text(hud, f"{name}.bands.label{i}", label, cap, x + col / 2, label_y, layer.mat("text"),
                         align="CENTER", z=0.003)[0])
        verts = [(hx(x), 0, 0), (hx(x + col), 0, 0), (hx(x + col), -1, 0), (hx(x), -1, 0)]
        bar = base.mesh_object(f"{name}.bands.bar{i}", verts, [(0, 1, 2, 3)], layer.mat("accent"), hud,
                               (0, hy(zero), 0.0025))
        _overlay_visibility(bar)
        objs.append(bar)
        for frame, values in losses:
            length = depth * min(values[i], max_db) / max_db * HUD_H
            key(bar, "scale", frame, (1.0, max(length, 1e-4), 1.0), "CONSTANT")
    show(objs, [window])


def travel_ruler(cam, name: str, length_m: float, marks: list[tuple[float, str]], ticks: list[float],
                 labels: list[tuple[float, str]], trips: list[tuple[float, float, float]], window,
                 y: float = 0.64) -> None:
    """A distance ruler above the lower third: the camera at the left end, ``marks`` (m, label) below
    the line, event ``ticks`` (m) and ``labels`` (m, text) above it. Each trip (emit frame, arrive
    frame, distance m) is a dot that leaves the event's tick on its frame and reaches the camera on
    the arrival frame, with a counter of the seconds on the way (0.1 s steps; the exact time when it
    arrives). A trip that arrives on its frame (synced) is a dot at the camera."""
    hud = base.hud_of(cam)
    layer = Layer(f"{name}.ruler")
    fps = base.story.FPS
    x0, x1 = 0.08, 0.93
    xm = lambda m: x0 + m / length_m * (x1 - x0)  # noqa: E731
    cap = 0.02
    objs = [rounded(hud, f"{name}.ruler.panel", 0.05, y - 0.095, 0.95, y + 0.05, 0.008, layer.mat("panel", 0.72),
                    z=0.0015),
            rect(hud, f"{name}.ruler.axis", x0, y - 0.002, x1, y + 0.002, layer.mat("muted"), z=0.002),
            disc(hud, f"{name}.ruler.camera", x0, y, 0.011, layer.mat("text"), hole=0.006),
            text(hud, f"{name}.ruler.camera_label", "camera", cap, x0, y + 0.04, layer.mat("muted"), align="CENTER",
                 z=0.003)[0]]
    for i, (m, label) in enumerate(marks):
        objs.append(rect(hud, f"{name}.ruler.mark{i}", xm(m) - 0.001, y, xm(m) + 0.001, y + 0.012, layer.mat("muted"),
                         z=0.002))
        objs.append(text(hud, f"{name}.ruler.mark_label{i}", label, cap, xm(m), y + 0.04, layer.mat("muted"),
                         align="CENTER", z=0.003)[0])
    for i, m in enumerate(ticks):
        objs.append(rect(hud, f"{name}.ruler.tick{i}", xm(m) - 0.0015, y - 0.018, xm(m) + 0.0015, y, layer.mat("text"),
                         z=0.002))
    for i, (m, label) in enumerate(labels):
        objs.append(text(hud, f"{name}.ruler.label{i}", label, cap, xm(m), y - 0.058, layer.mat("text"), align="CENTER",
                         z=0.003)[0])
    show(objs, [window])
    for i, (emit, arrive, m) in enumerate(trips):
        mover = base.empty(f"{name}.ruler.trip{i}", parent=hud)
        dot = disc(mover, f"{name}.ruler.dot{i}", x0, y, 0.012, layer.mat("accent"), z=0.004)
        travel = (arrive - emit) / fps
        key(mover, "location", 0, (0, 0, 0), "CONSTANT")
        if arrive > emit:
            key(mover, "location", emit, ((xm(m) - x0) * HUD_W, 0, 0), "LINEAR")
            key(mover, "location", arrive, (0, 0, 0), "CONSTANT")
        hold = arrive + 18
        base.visible(dot, [(round(emit), round(hold))], recursive=False)
        steps = int(round(travel * 10))
        for k in range(steps):  # 0.0 s, 0.1 s, ... on the way
            label = text(mover, f"{name}.ruler.count{i}_{k}", f"{k / 10:.1f} s", cap, x0, y - 0.022, layer.mat("accent"),
                         align="CENTER", z=0.004)[0]
            base.visible(label, [(round(emit + k * fps / 10), round(emit + (k + 1) * fps / 10) - 1)], recursive=False)
        final = text(mover, f"{name}.ruler.count{i}_end", f"{travel:.1f} s", cap, x0, y - 0.022, layer.mat("accent"),
                     bold=True, align="CENTER", z=0.004)[0]
        base.visible(final, [(round(arrive), round(hold))], recursive=False)


def map_inset(cam, name: str, track: list[tuple[float, float, float]], radius_m: float, window, cone_deg: float,
              shade: tuple[int, int] | None = None, top: float = 0.05, right: float = 0.95, size: float = 0.30) -> None:
    """A map seen from above at the upper right, the camera in the middle looking up: a ring at
    ``radius_m``, the camera's view cone (``cone_deg`` wide), and a dot keyed to the track's
    (frame, x, y) positions in metres relative to the camera (x right, y ahead). With ``shade`` (a
    frame window) the rear half is shaded: where the rear cue acts."""
    hud = base.hud_of(cam)
    layer = Layer(f"{name}.map")
    w = size * HUD_H / HUD_W
    cx, cy = right - w / 2, top + size / 2
    ring = 0.38 * size  # the ring's radius as a fraction of the height
    scale = ring * HUD_H / radius_m  # HUD metres per scene metre
    objs = [rounded(hud, f"{name}.map.panel", right - w, top, right, top + size, 0.008, layer.mat("panel", 0.86),
                    z=0.0015),
            disc(hud, f"{name}.map.ring", cx, cy, ring + 0.003, layer.mat("muted"), hole=ring - 0.003, z=0.002)]
    half = math.radians(cone_deg / 2)
    reach = 1.25 * ring * HUD_H
    ox, oy = hx(cx), hy(cy)
    fan = [(ox, oy, 0)] + [(ox + reach * math.sin(a), oy + reach * math.cos(a), 0)
                           for a in [-half + 2 * half * i / 12 for i in range(13)]]
    cone = base.mesh_object(f"{name}.map.cone", fan, [tuple(range(len(fan)))], layer.mat("accent", 0.22), hud,
                            (0, 0, 0.0018))
    _overlay_visibility(cone)
    objs += [cone, disc(hud, f"{name}.map.camera", cx, cy, 0.009, layer.mat("text"), z=0.0025)]
    show(objs, [window])
    if shade:
        segs = 24
        r = 1.18 * ring * HUD_H
        pts = [(ox, oy, 0)] + [(ox + r * math.cos(math.pi + math.pi * i / segs), oy + r * math.sin(math.pi + math.pi * i / segs), 0)
                               for i in range(segs + 1)]
        back = base.mesh_object(f"{name}.map.rear", pts, [tuple(range(len(pts)))], layer.mat("muted", 0.3), hud,
                                (0, 0, 0.0016))
        _overlay_visibility(back)
        show([back], [shade])
    mover = base.empty(f"{name}.map.mover", parent=hud)
    dot = disc(mover, f"{name}.map.dot", cx, cy, 0.012, layer.mat("accent"), z=0.003)
    for frame, x, y in track:
        key(mover, "location", frame, (x * scale, y * scale, 0.0))
    show([dot], [window])


def stereo_bar(cam, name: str, marks: list[tuple[int, float]], window, y: float = 0.79, hold: int = 24) -> None:
    """A line across the whole width of the frame with "L" and "R" at its ends: for each (frame, u)
    a mark at the place on the screen (u from -1 at the left edge to 1 at the right) where a sound is
    heard, shown for ``hold`` frames from its frame."""
    hud = base.hud_of(cam)
    layer = Layer(f"{name}.stereo")
    objs = [rect(hud, f"{name}.stereo.line", 0.0, y - 0.002, 1.0, y + 0.002, layer.mat("muted", 0.8), z=0.002),
            rect(hud, f"{name}.stereo.centre", 0.4985, y - 0.012, 0.5015, y + 0.012, layer.mat("muted", 0.8), z=0.002)]
    for i, body in enumerate(("L", "R")):
        objs.append(text(hud, f"{name}.stereo.{body}", body, 0.022, 0.05 if i == 0 else 0.95, y - 0.018,
                         layer.mat("text"), bold=True, align="LEFT" if i == 0 else "RIGHT")[0])
    show(objs, [window])
    for i, (frame, u) in enumerate(marks):
        dot = disc(hud, f"{name}.stereo.mark{i}", 0.5 + 0.5 * u, y, 0.014, layer.mat("accent"), z=0.003)
        show([dot], [(frame, min(frame + hold - 1, window[1]))])


def lobe_map(cam, name: str, track: list[tuple[float, float, float]], radius_m: float, window,
             outline: list[list[tuple[float, float]]], lobes: list[tuple[list[tuple[float, float]], str, float, tuple[int, int]]],
             top: float = 0.05, right: float = 0.95, size: float = 0.30) -> None:
    """A map seen from above at the upper right, centred on a standing object: its ``outline``
    (polygons in metres), a ring at ``radius_m``, filled ``lobes`` (points in metres around the
    centre, colour name, opacity, frame window) and a dot keyed to the track's (frame, x, y), x to
    the right and y up on the map."""
    hud = base.hud_of(cam)
    layer = Layer(f"{name}.lobes")
    w = size * HUD_H / HUD_W
    cx, cy = right - w / 2, top + size / 2
    ring = 0.4 * size
    scale = ring * HUD_H / radius_m
    ox, oy = hx(cx), hy(cy)
    objs = [rounded(hud, f"{name}.lobes.panel", right - w, top, right, top + size, 0.008, layer.mat("panel", 0.86),
                    z=0.0015),
            disc(hud, f"{name}.lobes.ring", cx, cy, ring + 0.002, layer.mat("muted"), hole=ring - 0.002, z=0.002)]
    for i, poly in enumerate(outline):
        pts = [(ox + x * scale, oy + y * scale, 0) for x, y in poly]
        obj = base.mesh_object(f"{name}.lobes.outline{i}", pts, [tuple(range(len(pts)))], layer.mat("text"), hud,
                               (0, 0, 0.0026))
        _overlay_visibility(obj)
        objs.append(obj)
    show(objs, [window])
    for i, (pts_m, colour_name, alpha, win) in enumerate(lobes):
        pts = [(ox, oy, 0)] + [(ox + x * scale, oy + y * scale, 0) for x, y in pts_m]
        n = len(pts_m)
        faces = [(0, 1 + j, 1 + (j + 1) % n) for j in range(n)]
        obj = base.mesh_object(f"{name}.lobes.lobe{i}", pts, faces, layer.mat(colour_name, alpha), hud,
                               (0, 0, 0.0018 + 0.0002 * i))
        _overlay_visibility(obj)
        show([obj], [win])
    mover = base.empty(f"{name}.lobes.mover", parent=hud)
    dot = disc(mover, f"{name}.lobes.dot", cx, cy, 0.012, layer.mat("accent"), z=0.003)
    for frame, x, y in track:
        key(mover, "location", frame, (x * scale, y * scale, 0.0))
    show([dot], [window])


def sight_map(cam, name: str, window, region: tuple[float, float, float, float],
              blocks: list[tuple[float, float, float, float]], listener: list[tuple[float, float, float]],
              source: list[tuple[float, float, float]], open_frames: list[tuple[int, int]],
              top: float = 0.05, right: float = 0.95, width: float = 0.26) -> None:
    """A map seen from above at the upper right of the ``region`` (x0, y0, x1, y1 in metres, +Y up):
    the ``blocks`` (rectangles in metres) that occlude, a dot each for the listener and the source
    keyed to their (frame, x, y), and the line between them: accent within ``open_frames``, muted
    while something is in the way."""
    hud = base.hud_of(cam)
    layer = Layer(f"{name}.sight")
    x0m, y0m, x1m, y1m = region
    scale = width * HUD_W / (x1m - x0m)  # HUD metres per scene metre
    height = (y1m - y0m) * scale / HUD_H
    pad = 0.012
    left = right - width

    def at(x: float, y: float) -> tuple[float, float]:
        return hx(left) + (x - x0m) * scale, hy(top + height) + (y - y0m) * scale

    objs = [rounded(hud, f"{name}.sight.panel", left - pad * HUD_H / HUD_W, top - pad, right + pad * HUD_H / HUD_W,
                    top + height + pad, 0.008, layer.mat("panel", 0.86), z=0.0015)]
    for i, (a, b, c, d) in enumerate(blocks):
        (ax, ay), (cx, cy) = at(max(a, x0m), max(b, y0m)), at(min(c, x1m), min(d, y1m))
        obj = base.mesh_object(f"{name}.sight.block{i}", [(ax, ay, 0), (cx, ay, 0), (cx, cy, 0), (ax, cy, 0)],
                               [(0, 1, 2, 3)], layer.mat("muted", 0.9), hud, (0, 0, 0.002))
        _overlay_visibility(obj)
        objs.append(obj)
    show(objs, [window])
    thick = 0.0035 * HUD_H
    for state, colour_name, wins in (("open", "accent", open_frames), ("blocked", "muted", None)):
        bar = base.mesh_object(f"{name}.sight.{state}", [(0, -thick, 0), (1, -thick, 0), (1, thick, 0), (0, thick, 0)],
                               [(0, 1, 2, 3)], layer.mat(colour_name), hud, (0, 0, 0.0024))
        _overlay_visibility(bar)
        for (frame, lx, ly), (_, sx, sy) in zip(listener, source):
            (ax, ay), (bx, by) = at(lx, ly), at(sx, sy)
            key(bar, "location", frame, (ax, ay, 0.0024))
            key(bar, "rotation_euler", frame, (0, 0, math.atan2(by - ay, bx - ax)))
            key(bar, "scale", frame, (math.hypot(bx - ax, by - ay), 1, 1))
        if wins is None:  # blocked: the frames of the window outside the open ones
            wins, f = [], window[0]
            for a, b in sorted(open_frames):
                if a > f:
                    wins.append((f, a - 1))
                f = max(f, b + 1)
            if f <= window[1]:
                wins.append((f, window[1]))
        show([bar], wins)
    for label, track, colour_name, r in (("listener", listener, "text", 0.010), ("source", source, "accent", 0.012)):
        mover = base.empty(f"{name}.sight.{label}", parent=hud)
        dot = disc(mover, f"{name}.sight.{label}.dot", 0.0, 0.0, r, layer.mat(colour_name), z=0.003)
        for frame, x, y in track:
            px, py = at(x, y)
            key(mover, "location", frame, (px - hx(0.0), py - hy(0.0), 0.0))
        show([dot], [window])


def plan_map(cam, name: str, window, region: tuple[float, float, float, float],
             paths: list[tuple[list[tuple[float, float]], str, float]],
             marks: list[tuple[float, float, str, float, list[tuple[int, int]]]],
             movers: list[tuple[list[tuple[float, float, float]], str, float]],
             top: float = 0.05, right: float = 0.95, width: float = 0.22) -> None:
    """A plan seen from above at the upper right of the ``region`` (x0, y0, x1, y1 in metres, +Y up):
    ``paths`` (closed polylines in metres, colour name, width in metres), ``marks`` (x, y, colour
    name, radius as a fraction of the height, frame windows) and ``movers`` (a dot keyed to the
    track's (frame, x, y), colour name, radius)."""
    hud = base.hud_of(cam)
    layer = Layer(f"{name}.plan")
    x0m, y0m, x1m, y1m = region
    scale = width * HUD_W / (x1m - x0m)
    height = (y1m - y0m) * scale / HUD_H
    pad = 0.012
    left = right - width

    def at(x: float, y: float) -> tuple[float, float]:
        return hx(left) + (x - x0m) * scale, hy(top + height) + (y - y0m) * scale

    objs = [rounded(hud, f"{name}.plan.panel", left - pad * HUD_H / HUD_W, top - pad, right + pad * HUD_H / HUD_W,
                    top + height + pad, 0.008, layer.mat("panel", 0.86), z=0.0015)]
    for i, (pts, colour_name, w_m) in enumerate(paths):
        verts, faces, n = [], [], len(pts)
        for j, (x, y) in enumerate(pts):
            (px, py), (qx, qy) = pts[j - 1], pts[(j + 1) % n]
            dx, dy = qx - px, qy - py
            norm = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / norm * w_m / 2, dx / norm * w_m / 2
            for sx, sy in ((x + nx, y + ny), (x - nx, y - ny)):
                verts.append((*at(sx, sy), 0))
        faces = [(2 * j, 2 * ((j + 1) % n), 2 * ((j + 1) % n) + 1, 2 * j + 1) for j in range(n)]
        obj = base.mesh_object(f"{name}.plan.path{i}", verts, faces, layer.mat(colour_name, 0.9), hud, (0, 0, 0.002))
        _overlay_visibility(obj)
        objs.append(obj)
    show(objs, [window])
    for i, (x, y, colour_name, r, wins) in enumerate(marks):
        px, py = at(x, y)
        dot = disc(hud, f"{name}.plan.mark{i}", (px - hx(0.0)) / HUD_W, (hy(0.0) - py) / HUD_H, r, layer.mat(colour_name),
                   z=0.0026)
        show([dot], wins)
    for i, (track, colour_name, r) in enumerate(movers):
        mover = base.empty(f"{name}.plan.mover{i}", parent=hud)
        dot = disc(mover, f"{name}.plan.mover{i}.dot", 0.0, 0.0, r, layer.mat(colour_name), z=0.003)
        for frame, x, y in track:
            px, py = at(x, y)
            key(mover, "location", frame, (px - hx(0.0), py - hy(0.0), 0.0))
        show([dot], [window])
