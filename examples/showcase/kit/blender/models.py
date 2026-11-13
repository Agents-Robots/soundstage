"""Low-poly models built from primitives, in real dimensions (in Blender).

Vehicles face -Y (Blender's front view) with their origin on the centre line, ``VEHICLE_Z`` above
the ground; their wheels are children named ``*.wheel*`` that ``drive`` turns. Figures stand with
their origin between the feet. Buildings occlude sound; vehicles, figures and props do not
(``base.no_occlusion``): a scene builder decides what is solid enough to block a sound, and these
are not.
"""

from __future__ import annotations

import math

from mathutils import Vector

from . import base
from .base import box, cylinder, empty, key, mesh_object, sphere, surface

VEHICLE_Z = 0.6
"""Height of a vehicle's origin above the ground (m)."""


def _wheel(name: str, parent, x: float, y: float, r: float, width: float):
    hub = empty(f"{name}", (x, y, r - VEHICLE_Z), parent)
    hub["radius"] = r
    cylinder(f"{name}.tyre", r, width, (0, 0, 0), surface("tyre", 0.9), axis="X", sides=14, parent=hub)
    box(f"{name}.spoke", (width + 0.02, r * 1.1, r * 0.25), (0, 0, 0), surface("rim", 0.4), parent=hub)
    return hub


def car(name: str, paint: str = "car_red", lights: bool = False):
    """A hatchback: 4.3 x 1.8 x 1.5 m."""
    root = empty(name)
    z0 = -VEHICLE_Z
    box(f"{name}.body", (1.8, 4.3, 0.7), (0, 0, z0 + 0.18 + 0.35), surface(paint, 0.4), root)
    box(f"{name}.cabin", (1.66, 2.3, 0.62), (0, 0.25, z0 + 0.88 + 0.31), surface(paint, 0.4), root)
    box(f"{name}.glass", (1.7, 2.2, 0.48), (0, 0.25, z0 + 0.9 + 0.26), surface("glass", 0.15), root)
    for side in (-1, 1):
        _wheel(f"{name}.wheel_f{side}", root, side * 0.8, -1.35, 0.32, 0.24)
        _wheel(f"{name}.wheel_r{side}", root, side * 0.8, 1.35, 0.32, 0.24)
        box(f"{name}.head{side}", (0.36, 0.05, 0.14), (side * 0.6, -2.16, z0 + 0.7),
            surface("headlight", 0.3, "headlight", 6.0 if lights else 0.3), root)
        box(f"{name}.tail{side}", (0.3, 0.05, 0.14), (side * 0.65, 2.16, z0 + 0.72),
            surface("taillight", 0.3, "taillight", 3.0 if lights else 0.2), root)
    base.no_occlusion(root)
    return root


def ambulance(name: str, lights: bool = True):
    """A van ambulance: 5.6 x 2.0 x 2.6 m, white with a red band and a blue light bar. Returns the
    root; the light bar is ``<name>.lightbar`` (an empty at its centre, 2.65 m above the ground)."""
    root = empty(name)
    z0 = -VEHICLE_Z
    box(f"{name}.box", (2.0, 3.9, 2.25), (0, 0.85, z0 + 0.3 + 1.125), surface("white", 0.4), root)
    box(f"{name}.cab", (1.96, 1.7, 1.35), (0, -1.95, z0 + 0.3 + 0.675), surface("white", 0.4), root)
    box(f"{name}.cab_top", (1.9, 1.2, 0.75), (0, -1.6, z0 + 1.65 + 0.3), surface("white", 0.4), root)
    box(f"{name}.windscreen", (1.8, 0.05, 0.62), (0, -2.22, z0 + 1.62 + 0.3), surface("glass", 0.15), root)
    box(f"{name}.band", (2.03, 3.92, 0.28), (0, 0.85, z0 + 1.1), surface("ambulance_red", 0.4), root)
    box(f"{name}.band_cab", (1.99, 1.72, 0.28), (0, -1.95, z0 + 1.1), surface("ambulance_red", 0.4), root)
    bar = empty(f"{name}.lightbar", (0, -0.9, 2.65 - VEHICLE_Z), root)
    box(f"{name}.lightbar.base", (1.5, 0.3, 0.08), (0, 0, -0.06), surface("metal"), bar)
    for side in (-1, 1):
        lamp = box(f"{name}.lightbar.lamp{side}", (0.6, 0.28, 0.14), (side * 0.38, 0, 0.05),
                   base.glow(f"{name}.blue{side}", "siren_blue", 0.0), bar)
        lamp["blink_phase"] = 0 if side < 0 else 1
        _wheel(f"{name}.wheel_f{side}", root, side * 0.85, -1.9, 0.36, 0.26)
        _wheel(f"{name}.wheel_r{side}", root, side * 0.85, 1.9, 0.36, 0.26)
        box(f"{name}.head{side}", (0.3, 0.05, 0.16), (side * 0.65, -2.81, z0 + 0.75),
            surface("headlight", 0.3, "headlight", 6.0 if lights else 0.3), root)
    base.no_occlusion(root)
    return root


def blink(root, frames: list[tuple[float, float]], period_s: float = 0.5, on: float = 25.0, off: float = 0.3) -> None:
    """Alternate the lamps marked ``blink_phase`` 0 and 1 (an ambulance's light bar, a crossing's red
    lamps) within frame windows, at emission strengths ``on`` and ``off``."""
    lamps = [o for o in root.children_recursive if "blink_phase" in o]
    for lamp in lamps:
        sock = base.emission_socket(lamp.active_material)
        key(sock, "default_value", 0, 0.0, "CONSTANT")
        for a, b in frames:
            f, half = a, period_s * base.story.FPS / 2
            lit = lamp["blink_phase"] == 0
            while f < b:
                key(sock, "default_value", f, on if lit else off, "CONSTANT")
                lit = not lit
                f += half
            key(sock, "default_value", b, 0.0, "CONSTANT")


def truck(name: str):
    """A box truck: 8 x 2.5 x 3.5 m."""
    root = empty(name)
    z0 = -VEHICLE_Z
    box(f"{name}.cab", (2.4, 2.1, 2.5), (0, -2.9, z0 + 0.55 + 1.25), surface("truck_cab", 0.4), root)
    box(f"{name}.windscreen", (2.2, 0.05, 0.9), (0, -3.96, z0 + 2.3), surface("glass", 0.15), root)
    box(f"{name}.box", (2.5, 5.6, 2.9), (0, 1.1, z0 + 0.6 + 1.45), surface("truck_box", 0.6), root)
    box(f"{name}.chassis", (2.0, 7.6, 0.3), (0, 0.0, z0 + 0.55), surface("metal"), root)
    for side in (-1, 1):
        _wheel(f"{name}.wheel_f{side}", root, side * 1.05, -2.8, 0.5, 0.3)
        _wheel(f"{name}.wheel_r{side}", root, side * 1.05, 2.4, 0.5, 0.3)
    base.no_occlusion(root)
    return root


def scooter(name: str, rider: bool = True):
    """A scooter, 1.8 m long, with a seated rider."""
    root = empty(name)
    z0 = -VEHICLE_Z
    for i, y in enumerate((-0.65, 0.65)):
        _wheel(f"{name}.wheel{i}", root, 0, y, 0.25, 0.12)
    box(f"{name}.body", (0.42, 1.0, 0.45), (0, 0.25, z0 + 0.55), surface("scooter", 0.4), root)
    box(f"{name}.floor", (0.36, 0.6, 0.08), (0, -0.25, z0 + 0.32), surface("metal"), root)
    box(f"{name}.column", (0.12, 0.12, 0.8), (0, -0.62, z0 + 0.75), surface("scooter", 0.4), root)
    box(f"{name}.bar", (0.7, 0.06, 0.06), (0, -0.62, z0 + 1.15), surface("metal"), root)
    box(f"{name}.seat", (0.32, 0.6, 0.1), (0, 0.3, z0 + 0.82), surface("tyre"), root)
    if rider:
        box(f"{name}.rider.torso", (0.4, 0.26, 0.6), (0, 0.25, z0 + 1.15), surface("jacket"), root)
        sphere(f"{name}.rider.helmet", 0.16, (0, 0.2, z0 + 1.6), surface("white", 0.3), root)
        for side in (-1, 1):
            box(f"{name}.rider.thigh{side}", (0.13, 0.5, 0.13), (side * 0.12, 0.0, z0 + 0.9), surface("trousers"), root)
            box(f"{name}.rider.shin{side}", (0.12, 0.12, 0.5), (side * 0.12, -0.25, z0 + 0.6), surface("trousers"), root)
    base.no_occlusion(root)
    return root


def motorbike(name: str, paint: str = "bike_green", lights: bool = True):
    """A motorbike, 2.1 m long, with its rider and a headlight; faces -Y like the other vehicles."""
    root = empty(name)
    z0 = -VEHICLE_Z
    for i, y in enumerate((-0.72, 0.72)):
        _wheel(f"{name}.wheel{i}", root, 0, y, 0.32, 0.14)
    box(f"{name}.frame", (0.12, 1.3, 0.12), (0, 0, z0 + 0.62), surface("metal"), root)
    box(f"{name}.engine", (0.34, 0.5, 0.36), (0, 0.02, z0 + 0.45), surface("nozzle", 0.5), root)
    box(f"{name}.tank", (0.36, 0.55, 0.26), (0, -0.2, z0 + 0.88), surface(paint, 0.35), root)
    box(f"{name}.seat", (0.3, 0.6, 0.1), (0, 0.38, z0 + 0.86), surface("tyre"), root)
    box(f"{name}.tail", (0.24, 0.4, 0.14), (0, 0.72, z0 + 0.86), surface(paint, 0.35), root)
    box(f"{name}.fork", (0.08, 0.08, 0.7), (0, -0.66, z0 + 0.62), surface("rim", 0.4), root).rotation_euler = (
        math.radians(-22), 0, 0)
    box(f"{name}.exhaust", (0.1, 0.7, 0.1), (0.2, 0.45, z0 + 0.32), surface("rim", 0.3), root)
    box(f"{name}.bar", (0.72, 0.05, 0.05), (0, -0.5, z0 + 1.08), surface("metal"), root)
    box(f"{name}.head", (0.2, 0.08, 0.16), (0, -0.86, z0 + 0.95),
        surface("headlight", 0.3, "headlight", 30.0 if lights else 0.3), root)
    box(f"{name}.taillight", (0.14, 0.04, 0.06), (0, 0.93, z0 + 0.88),
        surface("taillight", 0.3, "taillight", 4.0 if lights else 0.2), root)
    box(f"{name}.rider.torso", (0.4, 0.28, 0.62), (0, 0.18, z0 + 1.25), surface("jacket"), root).rotation_euler = (
        math.radians(-20), 0, 0)
    sphere(f"{name}.rider.helmet", 0.17, (0, -0.02, z0 + 1.72), surface("bike_helmet", 0.25), root)
    for side in (-1, 1):
        box(f"{name}.rider.arm{side}", (0.1, 0.5, 0.1), (side * 0.22, -0.2, z0 + 1.28), surface("jacket"), root
            ).rotation_euler = (math.radians(30), 0, 0)
        box(f"{name}.rider.thigh{side}", (0.14, 0.5, 0.14), (side * 0.18, 0.18, z0 + 0.95), surface("trousers"), root)
        box(f"{name}.rider.shin{side}", (0.12, 0.12, 0.5), (side * 0.2, -0.04, z0 + 0.68), surface("trousers"), root)
    base.no_occlusion(root)
    return root


def drive(root, path: list[tuple[float, Vector]], heading_deg: float) -> None:
    """Key a vehicle along (frame, position) points (linear between them), facing ``heading_deg``
    (compass: 0 = +Y, counter-clockwise), and turn its wheels by the distance driven."""
    root.rotation_euler = (0, 0, math.radians(heading_deg + 180))  # the model faces -Y
    base.runs(root, "location", [[(f, p) for f, p in path]])
    dist = [0.0]
    for (_, a), (_, b) in zip(path, path[1:]):
        dist.append(dist[-1] + (b - a).length)
    for hub in [o for o in root.children if ".wheel" in o.name]:
        r = hub["radius"]
        base.runs(hub, "rotation_euler", [[(f, (d / r, 0, 0)) for (f, _), d in zip(path, dist)]])


def figure(name: str, shirt: str = "shirt", trousers: str = "trousers"):
    """A standing person, 1.75 m. Legs and arms are children pivoting at hip and shoulder
    (``<name>.leg_l`` ...), for ``walk``."""
    root = empty(name)
    box(f"{name}.torso", (0.42, 0.24, 0.62), (0, 0, 1.2), surface(shirt), root)
    sphere(f"{name}.head", 0.12, (0, 0, 1.64), surface("skin", 0.6), root)
    for side, tag_ in ((-1, "l"), (1, "r")):
        hip = empty(f"{name}.leg_{tag_}", (side * 0.11, 0, 0.9), root)
        box(f"{name}.leg_{tag_}.mesh", (0.15, 0.17, 0.88), (0, 0, -0.44), surface(trousers), hip)
        box(f"{name}.leg_{tag_}.shoe", (0.13, 0.27, 0.08), (0, -0.05, -0.86), surface("tyre"), hip)
        sh = empty(f"{name}.arm_{tag_}", (side * 0.27, 0, 1.47), root)
        box(f"{name}.arm_{tag_}.mesh", (0.1, 0.12, 0.62), (0, 0, -0.31), surface(shirt), sh)
    base.no_occlusion(root)
    return root


def walk(root, start: Vector, heading_deg: float, frame0: float, steps: int, step_m: float = 0.7,
         step_s: float = 0.5, first_s: float = 0.0) -> list[tuple[float, str]]:
    """Walk ``steps`` steps from ``start`` along ``heading_deg``, starting ``first_s`` after
    ``frame0``. Returns (contact frame, foot) of every step: the frame its heel lands."""
    fps = base.story.FPS
    direction = Vector((-math.sin(math.radians(heading_deg)), math.cos(math.radians(heading_deg)), 0))
    root.rotation_euler = (0, 0, math.radians(heading_deg + 180))
    f0 = frame0 + first_s * fps
    f1 = f0 + steps * step_s * fps
    end = start + direction * step_m * steps
    base.runs(root, "location", [[(frame0, start), (f0, start), (f1, end)]])
    legs = {s: next(o for o in root.children if o.name == f"{root.name}.leg_{s}") for s in "lr"}
    arms = {s: next(o for o in root.children if o.name == f"{root.name}.arm_{s}") for s in "lr"}
    swing = math.radians(24)
    contacts = []
    base.key(legs["l"], "rotation_euler", frame0, (0, 0, 0), "CONSTANT")
    base.key(legs["r"], "rotation_euler", frame0, (0, 0, 0), "CONSTANT")
    for i in range(steps + 1):
        f = f0 + i * step_s * fps
        lead = "l" if i % 2 == 0 else "r"
        trail = "r" if lead == "l" else "l"
        last = i == steps
        a = 0.0 if last else swing
        interp = "CONSTANT" if last else "LINEAR"
        # the leading leg reaches forward (-Y of the model: a negative angle about X) as its heel
        # lands; the arms swing the other way
        base.key(legs[lead], "rotation_euler", f, (-a, 0, 0), interp)
        base.key(legs[trail], "rotation_euler", f, (a, 0, 0), interp)
        base.key(arms[lead], "rotation_euler", f, (0.6 * a, 0, 0), interp)
        base.key(arms[trail], "rotation_euler", f, (-0.6 * a, 0, 0), interp)
        if i > 0:
            contacts.append((f, lead))
    return contacts


def busker(name: str):
    """A standing person playing an accordion: the figure, both arms forward holding the instrument
    at chest height, 0.3 m in front of the torso. Returns (root, accordion): ``accordion`` is an
    empty at the middle of the bellows (``<name>.accordion``), with the halves ``.left``, ``.right``
    and the bellows ``.bellows`` as children, for ``play_accordion``."""
    root = figure(name, shirt="jacket")
    for side in "lr":
        arm = next(o for o in root.children if o.name == f"{name}.arm_{side}")
        arm.rotation_euler = (math.radians(-62), 0, math.radians(18 if side == "l" else -18))
        arm["held"] = tuple(arm.rotation_euler)
    acc = empty(f"{name}.accordion", (0, -0.3, 1.15), root)
    acc["rest"] = tuple(acc.location)
    for side, x in (("left", -0.2), ("right", 0.2)):
        half = empty(f"{name}.accordion.{side}", (x, 0, 0), acc)
        box(f"{half.name}.case", (0.1, 0.2, 0.36), (0, 0, 0), surface("accordion", 0.35), half)
        if side == "right":
            box(f"{half.name}.keys", (0.03, 0.12, 0.32), (0.06, 0, 0), surface("white", 0.4), half)
    box(f"{name}.accordion.bellows", (0.3, 0.18, 0.32), (0, 0, 0), surface("bellows", 0.6), acc)
    base.no_occlusion(root)
    return root, acc


def play_accordion(acc, frames: tuple[float, float], lower_s: float = 0.6, period_s: float = 1.6) -> None:
    """Open and close the bellows (0.25 to 0.45 m between the halves) once per ``period_s`` between
    two frames, then lower the instrument and the arms over ``lower_s``."""
    fps = base.story.FPS
    a, b = frames
    left, right, bellows = (next(o for o in acc.children if o.name.endswith(s)) for s in (".left", ".right", ".bellows"))
    rest = Vector(acc["rest"])
    key(acc, "location", a, tuple(rest), "CONSTANT")
    f, opening = a, True
    while f < b:
        gap = 0.45 if opening else 0.25
        key(left, "location", f, (-gap / 2 - 0.05, 0, 0), "BEZIER")
        key(right, "location", f, (gap / 2 + 0.05, 0, 0), "BEZIER")
        key(bellows, "scale", f, (gap / 0.3, 1, 1), "BEZIER")
        opening = not opening
        f += period_s * fps / 2
    key(acc, "location", b, tuple(rest), "BEZIER")
    key(acc, "location", b + lower_s * fps, (rest.x, rest.y + 0.15, rest.z - 0.4), "CONSTANT")
    for arm in (o for o in acc.parent.children if ".arm_" in o.name):
        held = tuple(arm["held"])
        key(arm, "rotation_euler", a, held, "CONSTANT")
        key(arm, "rotation_euler", b, held, "BEZIER")
        key(arm, "rotation_euler", b + lower_s * fps, (math.radians(-25), 0, held[2] * 0.5), "CONSTANT")


# --- buildings and props -------------------------------------------------------------------------

def house(name: str, width: float, depth: float, height: float, wall: str, lit: float = 0.0, seed: int = 0,
          roof: str = "roof", coll=None):
    """A house with a gable roof along its front, origin at the middle of the front wall on the
    ground, front facing -Y. Windows are one object; ``lit`` is the share of lit windows."""
    import random
    rnd = random.Random(seed)
    root = empty(name, coll=coll)
    box(f"{name}.walls", (width, depth, height), (0, depth / 2, height / 2), surface(wall, 0.85), root, coll)
    rise = min(depth * 0.45, 4.5)
    verts = [(-width / 2 - 0.3, -0.4, height), (width / 2 + 0.3, -0.4, height), (width / 2 + 0.3, depth + 0.4, height),
             (-width / 2 - 0.3, depth + 0.4, height), (-width / 2 - 0.3, depth / 2, height + rise),
             (width / 2 + 0.3, depth / 2, height + rise)]
    faces = [(0, 1, 5, 4), (2, 3, 4, 5), (0, 4, 3), (1, 2, 5), (0, 3, 2, 1)]
    mesh_object(f"{name}.roof", verts, faces, surface(roof, 0.8), root, coll=coll)
    floors = max(int(height // 3.1), 1)
    cols = max(int(width // 3.0), 1)
    wverts, wfaces, mats = [], [], []
    for fl in range(floors):
        z = 1.2 + fl * 3.1 if fl else 1.0
        for c in range(cols):
            x = -width / 2 + (c + 0.5) * width / cols
            if fl == 0 and c == cols // 2:
                w, h, z_ = 1.1, 2.2, 0.0  # a door
            else:
                w, h, z_ = 1.0, 1.4, z
            i = len(wverts)
            wverts += [(x - w / 2, -0.03, z_), (x + w / 2, -0.03, z_), (x + w / 2, -0.03, z_ + h), (x - w / 2, -0.03, z_ + h)]
            wfaces.append((i, i + 1, i + 2, i + 3))
            mats.append(1 if (fl > 0 or c != cols // 2) and rnd.random() < lit else 0)
    win = mesh_object(f"{name}.windows", wverts, wfaces,
                      [surface("window", 0.2), surface("window_lit", 0.5, "window_lit", 2.5)], root, coll=coll)
    for poly, m in zip(win.data.polygons, mats):
        poly.material_index = m
    win["sfx_occluder"] = False
    return root


def church(name: str, coll=None):
    """A church: nave 12 x 26 x 12 m behind a tower 6 x 6 m, 26 m to the eaves of the spire, front
    facing -Y, origin at the middle of the tower's front on the ground. The belfry is open on all
    sides (20.8 to 24.4 m); the bell hangs in it on a pivot (``<name>.bell_pivot``, swing about X),
    its mouth ``BELL_Z`` above the ground."""
    root = empty(name, coll=coll)
    box(f"{name}.tower", (6, 6, 20.8), (0, 3, 10.4), surface("stone", 0.9), root, coll)
    for i, (x, y) in enumerate(((-2.5, 0.5), (2.5, 0.5), (-2.5, 5.5), (2.5, 5.5))):
        box(f"{name}.belfry_post{i}", (1.0, 1.0, 3.6), (x, y, 22.6), surface("stone", 0.9), root, coll)
    box(f"{name}.tower_top", (6, 6, 1.6), (0, 3, 25.2), surface("stone", 0.9), root, coll)
    verts = [(-3.2, -0.2, 26), (3.2, -0.2, 26), (3.2, 6.2, 26), (-3.2, 6.2, 26), (0, 3, 36)]
    mesh_object(f"{name}.spire", verts, [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4), (0, 3, 2, 1)],
                surface("slate", 0.6), root, coll=coll)
    box(f"{name}.nave", (12, 26, 12), (0, 6 + 13, 6), surface("stone", 0.9), root, coll)
    verts = [(-6.4, 6, 12), (6.4, 6, 12), (6.4, 32.4, 12), (-6.4, 32.4, 12), (0, 6, 18), (0, 32.4, 18)]
    mesh_object(f"{name}.nave_roof", verts, [(0, 3, 5, 4), (1, 4, 5, 2), (0, 4, 1), (2, 5, 3)],
                surface("roof_dark", 0.8), root, coll=coll)
    for i in range(4):
        box(f"{name}.window{i}", (0.05, 1.4, 4.0), (-6.03, 10 + 5 * i, 6), surface("window", 0.3), root, coll)
    box(f"{name}.door", (2.0, 0.05, 3.4), (0, -0.04, 1.7), surface("wood", 0.7), root, coll)
    pivot = empty(f"{name}.bell_pivot", (0, 3, BELL_Z + 1.3), root, coll)
    cylinder(f"{name}.bell", 0.75, 1.1, (0, 0, -0.75), surface("bell", 0.35), parent=pivot, radius_top=0.42, sides=16)
    cylinder(f"{name}.bell_crown", 0.25, 0.25, (0, 0, -0.08), surface("bell", 0.35), parent=pivot, sides=8)
    for o in root.children_recursive:
        if o.name.startswith((f"{name}.window", f"{name}.belfry", f"{name}.door", f"{name}.bell", f"{name}.tower_top")):
            o["sfx_occluder"] = False
    return root


BELL_Z = 22.9
"""Height of the bell's mouth above the ground (m); the clapper strikes about 0.5 m higher."""


def ring_bell(pivot, strikes: list[float], swing_deg: float = 28.0, period_s: float = 2.0) -> None:
    """Swing the bell so that it reaches the end of a swing (where the clapper strikes) on each
    strike frame: alternately to either side, with a half period before the first."""
    fps = base.story.FPS
    half = period_s * fps / 2
    keys = [(strikes[0] - half, 0.0)]
    for i, f in enumerate(strikes):
        side = 1 if i % 2 == 0 else -1
        keys.append((f, side * math.radians(swing_deg)))
    keys.append((strikes[-1] + half, 0.0))
    for f, a in keys:
        key(pivot, "rotation_euler", f, (a, 0, 0), "BEZIER")


def tree(name: str, height: float = 8.0, seed: int = 0, coll=None):
    import random
    rnd = random.Random(seed)
    root = empty(name, coll=coll)
    cylinder(f"{name}.trunk", 0.18, height * 0.45, (0, 0, height * 0.225), surface("trunk"), parent=root, sides=8,
             radius_top=0.12, coll=coll)
    for i in range(3):
        r = height * (0.27 - 0.05 * i) * rnd.uniform(0.9, 1.1)
        sphere(f"{name}.crown{i}", r, (rnd.uniform(-0.4, 0.4), rnd.uniform(-0.4, 0.4), height * (0.55 + 0.15 * i)),
               surface("leaf" if i % 2 else "leaf_dark", 0.9), root, segments=8, rings=6, coll=coll)
    base.no_occlusion(root)
    return root


def street_lamp(name: str, on: bool, facing_deg: float = 0.0, coll=None):
    """A lamp post 5 m high with its arm over the road (``facing_deg``: compass direction of the arm)."""
    import bpy
    root = empty(name, coll=coll)
    root.rotation_euler = (0, 0, math.radians(facing_deg))
    cylinder(f"{name}.pole", 0.08, 5.0, (0, 0, 2.5), surface("metal", 0.5), parent=root, sides=8, coll=coll)
    box(f"{name}.arm", (0.08, 1.2, 0.08), (0, 0.55, 4.95), surface("metal", 0.5), root, coll)
    box(f"{name}.head", (0.3, 0.6, 0.16), (0, 1.1, 4.85), surface("lamp", 0.3, "lamp", 12.0 if on else 0.0), root, coll)
    if on:
        light = bpy.data.objects.new(f"{name}.light", bpy.data.lights.new(f"{name}.light", "POINT"))
        base.link(light, coll)
        light.parent = root
        light.location = (0, 1.1, 4.6)
        light.data.energy = 260.0
        light.data.color = base.linear("#ffd9a0")
        light.data.shadow_soft_size = 0.3
    base.no_occlusion(root)
    return root


def bench(name: str, coll=None):
    root = empty(name, coll=coll)
    box(f"{name}.seat", (1.8, 0.45, 0.06), (0, 0, 0.45), surface("wood"), root, coll)
    box(f"{name}.back", (1.8, 0.06, 0.4), (0, 0.22, 0.75), surface("wood"), root, coll)
    for side in (-1, 1):
        box(f"{name}.leg{side}", (0.06, 0.45, 0.45), (side * 0.8, 0, 0.225), surface("metal"), root, coll)
    base.no_occlusion(root)
    return root


def stage(name: str, coll=None):
    """An open-air stage facing -Y: a deck 16 x 10 m, 1.5 m high, a roof on four masts at 9 m, two
    loudspeaker towers beside the deck and a row of lights under the roof. Origin at the middle of
    the deck's front edge on the ground. Returns (root, lights): ``lights`` is a material whose
    emission strength can be keyed (``base.emission_socket``)."""
    root = empty(name, coll=coll)
    box(f"{name}.deck", (16, 10, 1.5), (0, 5, 0.75), surface("metal", 0.8), root, coll)
    box(f"{name}.back", (16, 0.3, 7.5), (0, 9.85, 5.25), surface("panel", 0.9), root, coll)
    for i, (x, y) in enumerate(((-7.8, 0.2), (7.8, 0.2), (-7.8, 9.8), (7.8, 9.8))):
        box(f"{name}.mast{i}", (0.4, 0.4, 9.0), (x, y, 4.5), surface("metal", 0.5), root, coll)
    box(f"{name}.roof", (17, 11, 0.6), (0, 5, 9.3), surface("panel", 0.8), root, coll)
    for side in (-1, 1):
        box(f"{name}.speakers{side}", (2.4, 2.0, 7.0), (side * 10, 1.5, 3.5), surface("panel", 0.9), root, coll)
        for k in range(3):
            cylinder(f"{name}.cone{side}{k}", 0.55, 0.05, (side * 10, 0.49, 1.6 + 2.0 * k), surface("metal", 0.6),
                     axis="Y", sides=16, parent=root, coll=coll)
    lights = base.glow(f"{name}.lights", "lamp", 0.0)
    for i in range(7):
        box(f"{name}.light{i}", (0.7, 0.5, 0.4), (-6 + 2 * i, 0.4, 8.7), lights, root, coll)
    base.no_occlusion(root)
    return root, lights


# --- doppler: race car, plane, railway -----------------------------------------------------------

def race_car(name: str, paint: str = "race_blue"):
    """A low racing car: 4.7 x 2.0 x 1.05 m, wedge nose, canopy, rear wing; faces -Y like the others."""
    root = empty(name)
    z0 = -VEHICLE_Z
    verts = [(-1.0, -2.35, z0 + 0.12), (1.0, -2.35, z0 + 0.12), (1.0, 2.25, z0 + 0.12), (-1.0, 2.25, z0 + 0.12),
             (-0.95, -2.3, z0 + 0.32), (0.95, -2.3, z0 + 0.32), (1.0, 2.25, z0 + 0.8), (-1.0, 2.25, z0 + 0.8)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    mesh_object(f"{name}.body", verts, faces, surface(paint, 0.3), root)
    box(f"{name}.canopy", (1.0, 1.5, 0.4), (0, 0.3, z0 + 0.85), surface("glass", 0.1), root)
    box(f"{name}.stripe", (0.36, 4.62, 0.02), (0, -0.04, z0 + 0.58), surface("white", 0.3), root)
    box(f"{name}.wing", (1.9, 0.45, 0.06), (0, 2.15, z0 + 1.05), surface("tyre", 0.5), root)
    for side in (-1, 1):
        box(f"{name}.wing_post{side}", (0.05, 0.2, 0.3), (side * 0.6, 2.1, z0 + 0.88), surface("tyre", 0.5), root)
        _wheel(f"{name}.wheel_f{side}", root, side * 0.88, -1.45, 0.34, 0.32)
        _wheel(f"{name}.wheel_r{side}", root, side * 0.88, 1.5, 0.35, 0.36)
    base.no_occlusion(root)
    return root


def plane(name: str, paint: str = "white", stripe: str = "car_red"):
    """A light high-wing plane: fuselage 7.5 m, span 10.5 m; nose towards -Y, origin at the wing's
    leading edge on the fuselage axis. The propeller is a translucent disc (``<name>.prop``)."""
    root = empty(name)
    box(f"{name}.fuselage", (1.1, 4.2, 1.3), (0, 0.6, 0), surface(paint, 0.4), root)
    verts = [(-0.55, 2.7, -0.4), (0.55, 2.7, -0.4), (0.55, 2.7, 0.65), (-0.55, 2.7, 0.65),
             (-0.12, 5.9, 0.1), (0.12, 5.9, 0.1), (0.12, 5.9, 0.4), (-0.12, 5.9, 0.4)]
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    mesh_object(f"{name}.tail", verts, faces, surface(paint, 0.4), root)
    box(f"{name}.nose", (0.95, 1.1, 1.0), (0, -1.95, -0.05), surface(paint, 0.4), root)
    box(f"{name}.stripe", (1.12, 6.6, 0.16), (0, 1.0, -0.15), surface(stripe, 0.4), root)
    box(f"{name}.windows", (1.14, 1.3, 0.45), (0, -0.6, 0.35), surface("glass", 0.15), root)
    box(f"{name}.wing", (10.5, 1.5, 0.14), (0, 0.15, 0.75), surface(paint, 0.4), root)
    box(f"{name}.stab", (3.4, 0.9, 0.08), (0, 5.55, 0.3), surface(paint, 0.4), root)
    box(f"{name}.fin", (0.08, 1.1, 1.4), (0, 5.55, 1.0), surface(stripe, 0.4), root)
    for side in (-1, 1):
        box(f"{name}.strut{side}", (2.0, 0.08, 0.06), (side * 1.4, 0.3, 0.1), surface("metal"), root).rotation_euler = (
            0, side * math.radians(-30), 0)
        box(f"{name}.leg{side}", (0.06, 0.08, 0.9), (side * 0.8, 0.3, -0.95), surface("metal"), root)
        cylinder(f"{name}.wheel{side}", 0.22, 0.14, (side * 0.9, 0.3, -1.35), surface("tyre"), axis="X", parent=root)
    cylinder(f"{name}.nose_wheel", 0.18, 0.12, (0, -1.9, -1.3), surface("tyre"), axis="X", parent=root)
    cylinder(f"{name}.spinner", 0.18, 0.35, (0, -2.65, -0.05), surface(stripe, 0.4), axis="Y", parent=root,
             radius_top=0.04)
    disc_mat = surface("prop_blur", 0.6)
    disc_mat.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = 0.35
    disc_mat.surface_render_method = "BLENDED"
    cylinder(f"{name}.prop", 0.95, 0.02, (0, -2.55, -0.05), disc_mat, axis="Y", sides=24, parent=root)
    base.no_occlusion(root)
    return root


def track(name: str, x0: float, x1: float, coll=None):
    """A railway track along X at y = 0 from x0 to x1: ballast, sleepers every 0.6 m, two rails
    (gauge 1.435 m) whose tops are 0.35 m above the ground."""
    root = empty(name, coll=coll)
    length = x1 - x0
    v, f = base.box_geometry(length, 3.4, 0.2, (x0 + x1) / 2, 0, 0.1)
    mesh_object(f"{name}.ballast", v, f, surface("ballast", 0.95), root, coll=coll)
    verts, faces = [], []
    n = int(length / 0.6)
    for i in range(n):
        v, f = base.box_geometry(0.25, 2.6, 0.12, x0 + 0.3 + 0.6 * i, 0, 0.24, offset=len(verts))
        verts += v
        faces += f
    mesh_object(f"{name}.sleepers", verts, faces, surface("wood_dark", 0.9), root, coll=coll)
    verts, faces = [], []
    for side in (-1, 1):
        v, f = base.box_geometry(length, 0.07, 0.07, (x0 + x1) / 2, side * 0.7525, 0.315, offset=len(verts))
        verts += v
        faces += f
    mesh_object(f"{name}.rails", verts, faces, surface("rail", 0.35), root, coll=coll)
    base.no_occlusion(root)
    return root


def crossing(name: str, road_width: float = 6.0, bell_y: float = -4.0, coll=None):
    """A level crossing at x = 0 on a track along X: the road along Y, on each side of the track a post
    with a crossbuck, two red lamps (``<name>.lamp{side}{i}``, for ``blink``) and a lowered barrier.
    The bell sits 3 m up beside the road on the -Y side, at ``bell_y`` (``<name>.bell``, an empty at
    its centre): on the post at -4, on a mast of its own farther out."""
    root = empty(name, coll=coll)
    v, f = base.box_geometry(road_width, 60.0, 0.06, 0, 0, 0.03)
    mesh_object(f"{name}.road", v, f, surface("asphalt", 0.9), root, coll=coll)
    for side in (-1, 1):
        y = side * 4.0
        x = -side * (road_width / 2 + 0.6)  # posts stand on the right of the road, seen from the track
        cylinder(f"{name}.post{side}", 0.07, 3.6, (x, y, 1.8), surface("white", 0.5), parent=root, sides=10, coll=coll)
        for k, rot in enumerate((45, -45)):
            arm = box(f"{name}.cross{side}{k}", (0.05, 1.3, 0.2), (x, y, 2.55), surface("white", 0.5), root, coll)
            arm.rotation_euler = (math.radians(rot), 0, 0)
        box(f"{name}.lampboard{side}", (0.08, 1.0, 0.36), (x, y, 1.9), surface("tyre", 0.6), root, coll)
        for i, dy in enumerate((-0.32, 0.32)):
            lamp = cylinder(f"{name}.lamp{side}{i}", 0.12, 0.06, (x - side * 0.06, y + dy, 1.9),
                            base.glow(f"{name}.lamp{side}{i}", "taillight", 0.0), axis="X", parent=root, coll=coll)
            lamp["blink_phase"] = i
        # the barrier: a striped arm across the road on the near side of the track
        pivot = empty(f"{name}.barrier{side}", (x, y + side * 1.2, 1.0), root, coll)
        for k in range(6):
            box(f"{name}.barrier{side}.seg{k}", (road_width / 6 + 0.01, 0.08, 0.08),
                (side * (k + 0.5) * road_width / 6 * 1.05, 0, 0), surface("taillight" if k % 2 else "white", 0.5),
                pivot, coll)
    bell = empty(f"{name}.bell", (road_width / 2 + 0.6, bell_y, 3.0), root, coll)
    if bell_y != -4.0:
        cylinder(f"{name}.bell.mast", 0.07, 3.0, (road_width / 2 + 0.6, bell_y, 1.5), surface("white", 0.5),
                 parent=root, sides=10, coll=coll)
    cylinder(f"{name}.bell.dome", 0.18, 0.16, (0, 0, 0), surface("bell", 0.35), parent=bell, radius_top=0.06, coll=coll)
    base.no_occlusion(root)
    return root


def train_cab(name: str, coll=None):
    """The inside of a locomotive cab around a camera looking along +X: a windscreen frame (one pane,
    no centre pillar in the view), the dashboard and side walls, origin at the eye point."""
    root = empty(name, coll=coll)
    wall = surface("cab", 0.7)
    box(f"{name}.dash", (0.6, 2.6, 0.5), (1.1, 0, -0.75), surface("cab_dark", 0.6), root, coll)
    box(f"{name}.sill", (0.1, 2.6, 0.5), (1.4, 0, -0.55), wall, root, coll)
    box(f"{name}.roof", (1.6, 2.6, 0.1), (0.8, 0, 0.62), wall, root, coll)
    for side in (-1, 1):
        box(f"{name}.post{side}", (0.1, 0.25, 1.2), (1.4, side * 1.2, 0.05), wall, root, coll)
        box(f"{name}.wall{side}", (1.6, 0.06, 0.55), (0.8, side * 1.3, -0.6), wall, root, coll)
    base.no_occlusion(root)
    return root



COURT = (23.77, 10.97)
"""Length and width of a tennis court (doubles), metres."""


def tennis_court(name: str, coll=None):
    """A hard court along X centred on the origin, the net along Y at x = 0: the playing area with
    its run-off, white lines, the net on two posts, an umpire's chair beyond the +Y post and a fence
    around."""
    root = empty(name, coll=coll)
    length, width = COURT
    v, f = base.box_geometry(length + 13.0, width + 9.0, 0.04, 0, 0, 0.02)
    mesh_object(f"{name}.runoff", v, f, surface("court_out", 0.85), root, coll=coll)
    v, f = base.box_geometry(length, width, 0.01, 0, 0, 0.045)
    mesh_object(f"{name}.court", v, f, surface("court", 0.8), root, coll=coll)
    line = surface("marking", 0.6)
    w = 0.05
    for sx in (-1, 1):  # baselines, service lines
        box(f"{name}.base{sx}", (w, width, 0.012), (sx * length / 2, 0, 0.05), line, root, coll)
        box(f"{name}.service{sx}", (w, 8.23, 0.012), (sx * 6.40, 0, 0.05), line, root, coll)
        box(f"{name}.mark{sx}", (0.1, w, 0.012), (sx * (length / 2 - 0.05), 0, 0.05), line, root, coll)
    for sy, half in ((-1, width / 2), (1, width / 2), (-1, 4.115), (1, 4.115)):  # doubles and singles sidelines
        box(f"{name}.side{sy}_{half:.1f}", (length, w, 0.012), (0, sy * half, 0.05), line, root, coll)
    box(f"{name}.centre", (12.8, w, 0.012), (0, 0, 0.05), line, root, coll)
    for sy in (-1, 1):
        cylinder(f"{name}.post{sy}", 0.05, 1.07, (0, sy * 6.4, 0.535), surface("metal", 0.5), parent=root, coll=coll)
    box(f"{name}.net", (0.03, 12.8, 0.86), (0, 0, 0.5), surface("net", 0.9), root, coll)
    box(f"{name}.net.tape", (0.05, 12.8, 0.06), (0, 0, 0.94), surface("white", 0.6), root, coll)
    chair = empty(f"{name}.chair", (0, 7.6, 0), root, coll)
    for dx in (-0.35, 0.35):
        for dy in (-0.35, 0.35):
            box(f"{name}.chair.leg{dx}{dy}", (0.06, 0.06, 2.0), (dx, dy, 1.0), surface("wood", 0.7), chair, coll)
    box(f"{name}.chair.seat", (0.8, 0.8, 0.08), (0, 0, 2.0), surface("wood", 0.7), chair, coll)
    box(f"{name}.chair.back", (0.8, 0.06, 0.6), (0, 0.38, 2.3), surface("wood", 0.7), chair, coll)
    umpire = figure(f"{name}.umpire", shirt="shirt_white", trousers="trousers")
    umpire.parent = chair
    umpire.location = (0, 0, 2.04 - 0.9)
    umpire.rotation_euler = (0, 0, 0)
    for leg in ("l", "r"):  # sitting: the thighs forward
        next(o for o in umpire.children if o.name.endswith(f".leg_{leg}")).rotation_euler = (-math.pi / 2, 0, 0)
    fx, fy, h = length / 2 + 6.0, width / 2 + 4.0, 3.0
    for i, (sx, sy, along) in enumerate(((0, 1, "x"), (-1, 0, "y"), (1, 0, "y"))):  # behind and at the ends
        size = (2 * fx, 0.04, h) if along == "x" else (0.04, 2 * fy, h)
        box(f"{name}.fence{i}", size, (sx * fx, sy * fy, h / 2), surface("fence", 0.9), root, coll)
    base.no_occlusion(root)
    return root


def tennis_player(name: str, shirt: str, facing: int, coll=None):
    """A player (``figure``) facing +X (``facing`` = 1) or -X (-1), with a racket held to the side
    towards -Y (forehand). The racket swings about a vertical axis at ``<name>.swing`` (for
    ``swing_racket``); at angle 0 it points straight ahead, its head 0.8 m from the axis and 1.0 m
    above the ground, where it meets the ball."""
    root = figure(name, shirt=shirt)
    root.rotation_euler = (0, 0, facing * math.pi / 2)  # the figure's front (-Y) to +X or -X
    swing = empty(f"{name}.swing", (0, 0, 0), None, coll)
    swing["facing"] = facing
    racket = empty(f"{name}.racket", (0, 0, 0), swing, coll)
    box(f"{name}.racket.handle", (0.55, 0.035, 0.035), (0.37, 0, 1.0), surface("racket", 0.5), racket, coll)
    ring = cylinder(f"{name}.racket.head", 0.15, 0.03, (0.8, 0, 1.0), surface("racket", 0.5), axis="Y", sides=14,
                    parent=racket, coll=coll)
    ring.scale = (1.0, 1.0, 1.25)
    base.no_occlusion(swing)
    return root, swing


def swing_racket(swing, hits: list[float], ready_deg: float = -60.0) -> None:
    """Forehand swings: from behind the player (on the -Y side) through the ball at each hit frame to
    a follow-through across the body; back to the ready position in between. Angles about Z from the
    player's facing direction, positive towards +Y."""
    facing = swing["facing"]
    base_deg = 0.0 if facing > 0 else 180.0
    sign = 1 if facing > 0 else -1

    def at(frame: float, deg: float) -> None:
        key(swing, "rotation_euler", frame, (0, 0, math.radians(base_deg + sign * deg)), "BEZIER")

    at(1, ready_deg)
    for h in hits:
        at(h - 14, ready_deg)
        at(h - 7, -150.0)
        at(h, 0.0)
        at(h + 5, 70.0)
        at(h + 20, ready_deg)


JET_ENGINE = (1.9, 0.0, 2.6)
"""Middle of the right engine of ``jet`` from its origin (the left one mirrored)."""
JET_NACELLE = 3.0
"""Length of a nacelle: the intake is half of it ahead of the engine's middle, the nozzle behind."""


def jet(name: str):
    """A business jet with two engines at the tail: fuselage 16 m, span 14 m, T-tail; nose towards -Y,
    origin on the ground under the middle between the engines. Each engine's fan (``<name>.fan_l``,
    ``.fan_r``) is a child that turns about Y."""
    root = empty(name)
    paint, trim = surface("jet_white", 0.35), surface("jet_trim", 0.4)
    box(f"{name}.fuselage", (2.0, 13.0, 2.0), (0, -5.5, 2.3), paint, root)
    verts = [(-1.0, -12.0, 1.3), (1.0, -12.0, 1.3), (1.0, -12.0, 3.3), (-1.0, -12.0, 3.3),
             (-0.35, -14.6, 1.9), (0.35, -14.6, 1.9), (0.35, -14.6, 2.5), (-0.35, -14.6, 2.5)]
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    mesh_object(f"{name}.nose", verts, faces, paint, root)
    verts = [(-1.0, 1.0, 1.3), (1.0, 1.0, 1.3), (1.0, 1.0, 3.3), (-1.0, 1.0, 3.3),
             (-0.3, 4.2, 2.6), (0.3, 4.2, 2.6), (0.3, 4.2, 3.3), (-0.3, 4.2, 3.3)]
    mesh_object(f"{name}.tailcone", verts, faces, paint, root)
    box(f"{name}.windscreen", (1.6, 0.9, 0.5), (0, -11.9, 3.05), surface("glass", 0.15), root)
    for i in range(6):
        box(f"{name}.window{i}", (2.04, 0.35, 0.3), (0, -9.5 + 1.1 * i, 2.75), surface("glass", 0.15), root)
    box(f"{name}.cheatline", (2.04, 13.0, 0.18), (0, -5.5, 2.3), trim, root)
    for side in (-1, 1):
        verts = [(side * 1.0, -8.2, 1.4), (side * 7.0, -5.2, 1.6), (side * 7.0, -4.1, 1.6), (side * 1.0, -5.0, 1.4)]
        wing = mesh_object(f"{name}.wing{side}", verts, [(0, 1, 2, 3) if side > 0 else (3, 2, 1, 0)], paint, root)
        wing.data.validate()
        box(f"{name}.winglet{side}", (0.08, 1.0, 1.2), (side * 7.0, -4.6, 2.2), trim, root)
        ex, ey, ez = side * JET_ENGINE[0], JET_ENGINE[1], JET_ENGINE[2]
        cylinder(f"{name}.nacelle{side}", 0.62, JET_NACELLE, (ex, ey, ez), paint, axis="Y", sides=16, parent=root)
        cylinder(f"{name}.lip{side}", 0.64, 0.12, (ex, ey - JET_NACELLE / 2, ez), trim, axis="Y", sides=16, parent=root)
        cylinder(f"{name}.nozzle{side}", 0.5, 0.3, (ex, ey + JET_NACELLE / 2 + 0.1, ez), surface("nozzle", 0.5),
                 axis="Y", sides=16, parent=root)
        box(f"{name}.pylon{side}", (1.0, 1.4, 0.25), (side * 1.2, ey, 2.6), paint, root)
        fan = empty(f"{name}.fan_{'l' if side < 0 else 'r'}", (ex, ey - JET_NACELLE / 2 - 0.02, ez), root)
        cylinder(f"{fan.name}.disc", 0.56, 0.02, (0, 0, 0), surface("fan", 0.6), axis="Y", sides=16, parent=fan)
        cylinder(f"{fan.name}.spinner", 0.16, 0.25, (0, -0.1, 0), surface("nozzle", 0.4), axis="Y", parent=fan,
                 radius_top=0.03)
        for b in range(8):
            blade = box(f"{fan.name}.blade{b}", (0.07, 0.03, 0.5), (0, -0.03, 0), surface("rim", 0.4), fan)
            a = 2 * math.pi * b / 8
            blade.location = (0.3 * math.sin(a), -0.03, 0.3 * math.cos(a))
            blade.rotation_euler = (0, a, 0)
        cylinder(f"{name}.wheel{side}", 0.35, 0.25, (side * 1.7, -5.0, 0.35), surface("tyre"), axis="X", parent=root)
        box(f"{name}.gear{side}", (0.1, 0.1, 1.1), (side * 1.5, -5.0, 0.9), surface("metal"), root)
    box(f"{name}.fin", (0.25, 2.6, 3.4), (0, 3.0, 4.6), paint, root).rotation_euler = (math.radians(-18), 0, 0)
    box(f"{name}.stab", (6.2, 1.4, 0.15), (0, 4.0, 6.2), paint, root)
    box(f"{name}.fin_trim", (0.27, 1.6, 0.6), (0, 3.3, 5.3), trim, root).rotation_euler = (math.radians(-18), 0, 0)
    cylinder(f"{name}.nose_wheel", 0.25, 0.18, (0, -12.0, 0.25), surface("tyre"), axis="X", parent=root)
    box(f"{name}.nose_gear", (0.1, 0.1, 1.2), (0, -12.0, 0.8), surface("metal"), root)
    base.no_occlusion(root)
    return root


def spin(obj, frames: tuple[int, int], rev_per_s: float, axis: int = 1) -> None:
    """Turn ``obj`` about one of its axes at a constant rate between two frames."""
    a, b = frames
    turns = 2 * math.pi * rev_per_s * (b - a) / base.story.FPS
    rot = [0.0, 0.0, 0.0]
    key(obj, "rotation_euler", a, tuple(rot))
    rot[axis] = turns
    key(obj, "rotation_euler", b, tuple(rot))


# --- interiors -----------------------------------------------------------------------------------
# Rooms are built around a camera standing at the origin and looking along +Y; their walls, floor and
# ceiling are separate boxes, so that the camera sees into the room. Nothing in them occludes: a room
# contains its camera and its sources.

def _area_light(name: str, location, size: float, energy: float, colour: str, parent, size_y: float | None = None):
    import bpy
    light = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
    base.link(light)
    light.parent = parent
    light.location = location
    light.data.shape = "RECTANGLE"
    light.data.size, light.data.size_y = size, size if size_y is None else size_y
    light.data.energy = energy
    light.data.color = base.linear(colour)
    return light


def _shell(name: str, root, x: tuple[float, float], y: tuple[float, float], height: float, wall: str, floor: str,
           ceiling: str, t: float = 0.3) -> None:
    (x0, x1), (y0, y1) = x, y
    w, d = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    box(f"{name}.floor", (w + 2 * t, d + 2 * t, t), (cx, cy, -t / 2), surface(floor, 0.7), root)
    box(f"{name}.ceiling", (w + 2 * t, d + 2 * t, t), (cx, cy, height + t / 2), surface(ceiling, 0.9), root)
    for side in (-1, 1):
        box(f"{name}.wall_x{side}", (t, d + 2 * t, height), (cx + side * (w + t) / 2, cy, height / 2), surface(wall, 0.9),
            root)
        box(f"{name}.wall_y{side}", (w, t, height), (cx, cy + side * (d + t) / 2, height / 2), surface(wall, 0.9), root)


def living_room(name: str):
    """A living room 5 m long (camera at 0.4 m from the wall behind it), 4.4 m wide, 2.6 m high: sofa,
    armchair, low table, rug, shelf, a window with daylight, a floor lamp."""
    root = empty(name)
    _shell(name, root, (-2.2, 2.2), (-0.4, 4.6), 2.6, "room_wall", "parquet", "white")
    box(f"{name}.rug", (2.4, 1.8, 0.02), (0.0, 3.4, 0.01), surface("rug", 0.95), root)
    box(f"{name}.sofa", (0.9, 2.2, 0.45), (-1.7, 3.2, 0.225), surface("sofa", 0.9), root)
    box(f"{name}.sofa_back", (0.25, 2.2, 0.85), (-2.05, 3.2, 0.425), surface("sofa", 0.9), root)
    box(f"{name}.chair", (0.8, 0.8, 0.45), (1.6, 2.2, 0.225), surface("sofa", 0.9), root)
    box(f"{name}.chair_back", (0.2, 0.8, 0.85), (1.95, 2.2, 0.425), surface("sofa", 0.9), root)
    box(f"{name}.table", (0.6, 1.0, 0.4), (-0.9, 3.2, 0.2), surface("wood", 0.6), root)
    box(f"{name}.shelf", (2.0, 0.35, 1.9), (0.6, 4.42, 0.95), surface("wood_dark", 0.7), root)
    for i in range(4):
        box(f"{name}.books{i}", (1.8, 0.25, 0.3), (0.6, 4.37, 0.35 + 0.45 * i), surface(("car_red", "shirt", "field",
            "white")[i], 0.8), root)
    box(f"{name}.window", (0.05, 1.4, 1.2), (2.18, 2.6, 1.45), surface("sky_window", 0.3, "sky_window", 1.5), root)
    cylinder(f"{name}.lamp_pole", 0.02, 1.6, (-1.9, 4.2, 0.8), surface("metal"), parent=root)
    cylinder(f"{name}.lamp_shade", 0.22, 0.3, (-1.9, 4.2, 1.65), surface("lamp", 0.5, "lamp", 2.0), parent=root,
             radius_top=0.14)
    _area_light(f"{name}.light", (0, 2.4, 2.55), 2.0, 70.0, "#ffe7c4", root)
    _area_light(f"{name}.window_light", (2.0, 2.6, 1.45), 1.2, 40.0, "#dfeeff", root).rotation_euler = (
        0, math.radians(-90), 0)
    base.no_occlusion(root)
    return root


def gym(name: str):
    """A sports hall 40 m long (camera 8 m from the wall behind it), 22 m wide, 9 m high: wooden
    floor with court lines, a basketball hoop at each end, wall bars, high windows, ceiling lights."""
    root = empty(name)
    _shell(name, root, (-11.0, 11.0), (-8.0, 32.0), 9.0, "gym_wall", "gym_floor", "gym_ceiling")
    lines = surface("gym_line", 0.6)
    for k, (sx, sy, x, y) in enumerate(((0.08, 36, -9.0, 12), (0.08, 36, 9.0, 12), (18, 0.08, 0, -6.0),
                                        (18, 0.08, 0, 30.0), (18, 0.08, 0, 12.0))):
        box(f"{name}.line{k}", (sx, sy, 0.01), (x, y, 0.005), lines, root)
    for y, facing in ((-6.6, 1), (30.6, -1)):
        hoop = basketball_hoop(f"{name}.hoop{'a' if facing > 0 else 'b'}")
        hoop.parent = root
        hoop.location = (0, y, 0)
        hoop.rotation_euler = (0, 0, 0 if facing < 0 else math.pi)
    for i in range(12):  # wall bars on the left
        box(f"{name}.bars{i}", (0.08, 0.9, 3.0), (-10.95, 2 + 1.1 * i, 1.5), surface("wood", 0.6), root)
    for side in (-1, 1):
        for i in range(8):
            box(f"{name}.window{side}_{i}", (0.05, 3.0, 1.6), (side * 10.98, -5 + 5 * i, 7.4),
                surface("sky_window", 0.3, "sky_window", 1.2), root)
    for i in range(4):
        for j in range(2):
            _area_light(f"{name}.light{i}{j}", (-5 + 10 * j, -2 + 9 * i, 8.9), 3.0, 450.0, "#f4f6ff", root)
            box(f"{name}.fixture{i}{j}", (3.0, 0.4, 0.08), (-5 + 10 * j, -2 + 9 * i, 8.95),
                surface("white", 0.3, "white", 1.5), root)
    base.no_occlusion(root)
    return root


def basketball_hoop(name: str):
    """A hoop on a post: backboard 1.8 x 1.05 m, rim at 3.05 m, 1.2 m in front of the post (-Y)."""
    root = empty(name)
    box(f"{name}.post", (0.15, 0.15, 3.6), (0, 0.3, 1.8), surface("metal", 0.5), root)
    box(f"{name}.arm", (0.1, 1.0, 0.1), (0, -0.2, 3.5), surface("metal", 0.5), root)
    box(f"{name}.board", (1.8, 0.05, 1.05), (0, -0.75, 3.45), surface("white", 0.4), root)
    box(f"{name}.square", (0.6, 0.06, 0.45), (0, -0.76, 3.3), surface("car_red", 0.5), root)
    for i in range(12):
        a = 2 * math.pi * i / 12
        box(f"{name}.rim{i}", (0.04, 0.13, 0.03), (0.23 * math.sin(a), -1.0 - 0.23 * math.cos(a), 3.05),
            surface("rim_orange", 0.4), root).rotation_euler = (0, 0, -a)
    base.no_occlusion(root)
    return root


def nave(name: str):
    """A church nave 30 m long (camera 2 m inside the west door), 12 m wide, 12 m high: stone floor,
    pillars 3.6 m to either side of the aisle, pews, an altar, tall windows."""
    root = empty(name)
    _shell(name, root, (-6.0, 6.0), (-2.0, 28.0), 12.0, "stone", "nave_floor", "nave_ceiling")
    box(f"{name}.aisle", (1.8, 26.0, 0.01), (0, 13.0, 0.005), surface("rug_red", 0.95), root)
    for side in (-1, 1):
        for i in range(7):
            y = 2.0 + 4.0 * i
            cylinder(f"{name}.pillar{side}_{i}", 0.45, 10.4, (side * 3.6, y, 5.2), surface("stone_light", 0.8),
                     parent=root, sides=16)
            box(f"{name}.capital{side}_{i}", (1.2, 1.2, 0.4), (side * 3.6, y, 10.6), surface("stone_light", 0.8), root)
            box(f"{name}.window{side}_{i}", (0.05, 1.6, 4.5), (side * 5.98, y + 2.0, 6.6),
                surface("stained", 0.3, "stained", 2.2), root)
        box(f"{name}.arcade{side}", (0.8, 26.0, 1.2), (side * 3.6, 14.0, 11.4), surface("stone_light", 0.8), root)
        for i in range(12):
            y = 4.0 + 1.1 * i
            box(f"{name}.pew{side}_{i}", (2.2, 0.45, 0.45), (side * 2.0, y, 0.225), surface("wood_dark", 0.7), root)
            box(f"{name}.pew_back{side}_{i}", (2.2, 0.08, 0.95), (side * 2.0, y + 0.25, 0.475), surface("wood_dark", 0.7),
                root)
    box(f"{name}.altar_step", (5.0, 3.0, 0.3), (0, 25.5, 0.15), surface("stone_light", 0.8), root)
    box(f"{name}.altar", (2.0, 0.9, 1.0), (0, 26.0, 0.8), surface("white", 0.6), root)
    cylinder(f"{name}.rose", 1.6, 0.05, (0, 27.97, 8.5), surface("stained", 0.3, "stained", 3.0), axis="Y", sides=24,
             parent=root)
    for i in range(4):
        _area_light(f"{name}.light{i}", (0, 2 + 7 * i, 11.8), 4.0, 900.0, "#ffe2b8", root, size_y=6.0)
    _area_light(f"{name}.altar_light", (0, 24.0, 6.0), 3.0, 400.0, "#ffd9a0", root)
    base.no_occlusion(root)
    return root


def grandstand(name: str, length: float, rows: int = 30, seed: int = 0, coll=None):
    """A grandstand along X, the seats rising away from the track (+Y) in rows 0.8 m deep and 0.5 m
    high, a back wall up to a flat roof; spectators as small boxes in five colours. Origin at the
    front of the lowest row on the ground; the roof's top is ``rows * 0.5 + 13.8`` m high, its front edge
    4.5 m in front of the origin."""
    import random
    rnd = random.Random(seed)
    root = empty(name, coll=coll)
    verts, faces = [], []
    for r in range(rows):
        v, f = base.box_geometry(length, 0.8, 0.5 * (r + 1), 0, 0.4 + 0.8 * r, 0.25 * (r + 1), len(verts))
        verts += v
        faces += f
    mesh_object(f"{name}.rows", verts, faces, surface("stone_light", 0.85), root, coll=coll)
    depth, roof = 0.8 * rows, rows * 0.5 + 13.5
    box(f"{name}.back", (length, 1.0, roof), (0, depth + 0.5, roof / 2), surface("hangar", 0.8), root, coll)
    box(f"{name}.roof", (length + 2, depth + 6, 0.6), (0, depth / 2 - 1.5, roof), surface("slate", 0.7), root, coll)
    for i in range(int(length // 12) + 1):
        box(f"{name}.column{i}", (0.4, 0.4, roof - 0.5 * rows), (-length / 2 + 12 * i, -2.0, (roof + 0.5 * rows) / 2),
            surface("metal", 0.5), root, coll)
    people = {c: ([], []) for c in ("car_red", "shirt", "white", "field", "jacket")}
    for r in range(1, rows, 1):
        x = -length / 2 + rnd.uniform(0.2, 0.8)
        while x < length / 2 - 0.5:
            if rnd.random() < 0.7:
                v, f = people[rnd.choice(list(people))]
                gv, gf = base.box_geometry(0.45, 0.35, 0.75, x, 0.8 * r + 0.3, 0.5 * (r + 1) + 0.37, len(v))
                v += gv
                f += gf
            x += rnd.uniform(0.55, 0.9)
    for c, (v, f) in people.items():
        mesh_object(f"{name}.people_{c}", v, f, surface(c, 0.8), root, coll=coll)
    base.no_occlusion(root)
    return root


# --- finale: train, fireworks --------------------------------------------------------------------

TRAIN_COACH, TRAIN_GAP, TRAIN_LOCO = 24.0, 1.0, 17.0
TRAIN_CAB = 3.5
"""Length of the locomotive's cab section at its front (m)."""


def train(name: str, coaches: int = 2, coll=None):
    """A locomotive and its coaches on the rails, facing -Y; origin at the middle of the front on the
    tops of the rails. Returns (root, emitters, cab_shell): emitters are empties ``front`` (horn, on
    the roof at the front) and ``roll0`` ... (under the middle of each vehicle); ``cab_shell`` are the
    objects that close the cab around a camera inside it (the front wall with its windscreen, the
    lamps), for a shot from inside to hide."""
    import bpy
    root = empty(name, coll=coll)
    paint, dark = surface("loco", 0.4), surface("loco_dark", 0.6)
    shell = [box(f"{name}.cab", (3.0, TRAIN_CAB, 3.0), (0, TRAIN_CAB / 2, 2.5), paint, root, coll),
             box(f"{name}.windscreen", (2.6, 0.05, 1.0), (0, -0.03, 3.2), surface("glass", 0.15), root, coll)]
    for side in (-1, 1):
        shell.append(box(f"{name}.headlamp{side}", (0.36, 0.05, 0.24), (side * 1.0, -0.03, 1.6),
                         surface("headlight", 0.3, "headlight", 12.0), root, coll))
    box(f"{name}.body", (3.0, TRAIN_LOCO - TRAIN_CAB, 3.0), (0, (TRAIN_LOCO + TRAIN_CAB) / 2, 2.5), paint, root, coll)
    box(f"{name}.stripe", (3.04, TRAIN_LOCO, 0.25), (0, TRAIN_LOCO / 2, 1.5), surface("white", 0.4), root, coll)
    box(f"{name}.roof_gear", (1.6, 8.0, 0.4), (0, 10.0, 4.2), dark, root, coll)
    lengths = [(0.0, TRAIN_LOCO)] + [(TRAIN_LOCO + TRAIN_GAP + k * (TRAIN_COACH + TRAIN_GAP), TRAIN_COACH)
                                     for k in range(coaches)]
    for k, (y0, length) in enumerate(lengths):
        box(f"{name}.frame{k}", (2.6, length - 0.5, 0.6), (0, y0 + length / 2, 0.7), dark, root, coll)
        for j, y in enumerate((y0 + 3.0, y0 + length - 3.0)):
            box(f"{name}.bogie{k}{j}", (2.4, 3.0, 0.6), (0, y, 0.3), surface("tyre", 0.8), root, coll)
        if k:
            box(f"{name}.coach{k}", (2.9, length, 3.0), (0, y0 + length / 2, 2.6), surface("coach", 0.45), root, coll)
            box(f"{name}.coach{k}.windows", (2.95, length - 2.0, 0.8), (0, y0 + length / 2, 2.9),
                surface("window_lit", 0.4, "window_lit", 1.5), root, coll)
            box(f"{name}.coach{k}.roof", (2.7, length, 0.3), (0, y0 + length / 2, 4.25), surface("slate", 0.6), root, coll)
    emitters = {"front": empty(f"{name}.front", (0, 0.3, 4.2), root, coll)}
    for k, (y0, length) in enumerate(lengths):
        emitters[f"roll{k}"] = empty(f"{name}.roll{k}", (0, y0 + length / 2, 0.3), root, coll)
    lamp = bpy.data.objects.new(f"{name}.beam", bpy.data.lights.new(f"{name}.beam", "SPOT"))
    base.link(lamp, coll)
    lamp.parent = root
    lamp.location = (0, -0.3, 1.8)
    lamp.rotation_euler = (math.radians(-86), 0, 0)  # along -Y, a little down
    lamp.data.energy, lamp.data.spot_size = 60000.0, math.radians(40)
    lamp.data.color = base.linear("#fff1d6")
    base.no_occlusion(root)
    return root, emitters, shell


def firework(name: str, centre: Vector, colour: str, frame: float, launch: Vector, sparks: int = 36,
             spread_m: float = 30.0, spark_m: float = 1.6) -> None:
    """A rocket rising from ``launch`` for 1.2 s, then a burst of sparks ``2 * spread_m`` across at
    ``centre`` on ``frame``, falling and fading out over 1.5 s."""
    import random
    mat = base.glow(f"{name}.glow", colour, 0.0)
    sock = base.emission_socket(mat)
    key(sock, "default_value", frame - 0.01, 0.0, "CONSTANT")
    key(sock, "default_value", frame, 18.0, "LINEAR")
    key(sock, "default_value", frame + 45, 0.0, "CONSTANT")
    rocket = sphere(f"{name}.rocket", 0.9, launch, base.glow(f"{name}.rocket_glow", "spark_gold", 40.0), segments=8,
                    rings=4)
    key(rocket, "location", frame - 36, tuple(launch), "LINEAR")
    key(rocket, "location", frame, tuple(centre), "CONSTANT")
    base.visible(rocket, [(frame - 36, frame - 1)])
    rnd = random.Random(name)
    for i in range(sparks):
        z = 1 - 2 * (i + 0.5) / sparks  # spread on a sphere (Fibonacci)
        a = i * math.pi * (3 - math.sqrt(5))
        d = Vector((math.sqrt(1 - z * z) * math.cos(a), math.sqrt(1 - z * z) * math.sin(a), z))
        spark = sphere(f"{name}.spark{i}", spark_m, centre, mat, segments=6, rings=4)
        out = centre + d * spread_m * rnd.uniform(0.85, 1.05)
        key(spark, "location", frame, tuple(centre), "BEZIER")
        key(spark, "location", frame + 15, tuple(out), "LINEAR")
        key(spark, "location", frame + 45, tuple(out + Vector((0, 0, -12))), "CONSTANT")
        base.visible(spark, [(frame, frame + 45)])
        base.no_occlusion(spark)
    base.no_occlusion(rocket)
