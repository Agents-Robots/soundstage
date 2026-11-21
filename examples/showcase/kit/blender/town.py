"""The town: main street, square, church, houses, lamps and trees (in Blender).

One layout for every section that plays in the town (``intro``, ``sources``, ``occlusion``,
``finale``), so that the same places look and sound the same. Coordinates in metres:

- The main street runs along X; its centre line is y = 0. Driving lanes are 3.5 m wide (lane
  centres at y = +-1.75; right-hand traffic: a car driving towards -X uses the lane at +1.75),
  parking lanes 2 m (centres at +-4.5), pavements 3.5 m; house fronts at y = +-9.
- The square opens to the north of the street for |x| <= 30, up to y = 75.
- The church stands opposite the square, south of the street, its tower front at (-14, -43.25),
  facing the square; the bell hangs 23 to 24 m above the ground, 62 m (horizontally) from
  (0, 13.75), where it stands right of the middle of a view across the street.
- With ``side_street`` (``finale``): a pedestrian street leaves the square's east side along X,
  centre line y = 46, house fronts at y = 41.5 and 50.5, to x = 130. Without it the town is the
  same as before, house for house (the side street's houses are drawn last).
"""

from __future__ import annotations

import math
import random

import bpy
from mathutils import Vector

from . import base, models
from .base import box, mesh_object, surface

LANE = 1.75
PARKING = 4.5
KERB = 5.5
FRONT = 9.0
STREET = (-260.0, 320.0)
SQUARE = (-30.0, 30.0, FRONT, 75.0)  # x0, x1, y0, y1
PLAZA = (-22.0, 22.0)
CHURCH_FRONT = Vector((-14.0, -43.25, 0.0))
SIDE_Y = 46.0
SIDE_HALF = 4.5
"""Centre line and half width (front to front) of the side street."""
SIDE_END = 130.0


def build(time_of_day: str, parked: list[tuple[float, float, str]] = (), seed: int = 7,
          side_street: bool = False, lit: float = 0.45) -> dict:
    """Build the town and return its named places (objects and positions).

    ``parked``: (x, y, paint) of parked cars, facing the direction of their lane's traffic; ``lit``:
    the share of lit windows at dusk.
    """
    rnd = random.Random(seed)
    dusk = time_of_day == "dusk"
    coll = base.collection("town")
    _ground(coll)
    lit = lit if dusk else 0.0
    _rows(rnd, lit, coll, side_street)
    if side_street:
        _side_street(rnd, lit, coll)
    church = models.church("church", coll=coll)
    church.location = CHURCH_FRONT
    church.rotation_euler = (0, 0, math.pi)  # front towards +Y, the square
    for i, x in enumerate(range(int(STREET[0]) + 10, int(STREET[1]), 30)):
        for side in (-1, 1):
            lamp = models.street_lamp(f"lamp.{i}.{side}", on=dusk, facing_deg=0 if side < 0 else 180, coll=coll)
            lamp.location = (x + (15 if side > 0 else 0), side * (KERB + 0.4), 0)
    for i, (x, y, h) in enumerate([(-22, 25, 9), (22, 25, 8), (-22, 50, 10), (22, 50, 9), (-12, 66, 8),
                                   (12, 66, 9), (-17, -20, 9), (17, -20, 8), (-17, -33, 10), (17, -33, 9)]):
        models.tree(f"tree.{i}", h, seed=i, coll=coll).location = (x, y, 0)
    b = models.bench("bench.0", coll=coll)
    b.location = (-9, 22, 0)
    b.rotation_euler = (0, 0, math.pi)
    for i, (x, y, paint) in enumerate(parked):
        c = models.car(f"parked.{i}", paint, lights=False)
        c.location = (x, y, models.VEHICLE_Z)
        c.rotation_euler = (0, 0, math.pi if y > 0 else 0.0)  # +y side: facing -X, -y side: +X
        c.rotation_euler.z += math.pi / 2
    bell_pivot = bpy.data.objects["church.bell_pivot"]
    return {"collection": coll, "church": church, "bell_pivot": bell_pivot,
            "bell": bpy.data.objects["church.bell"]}


def _ground(coll) -> None:
    x0, x1 = STREET
    box("ground", (3000, 3000, 0.2), (0, 0, -0.1), surface("grass", 0.95), coll=coll)
    box("road", (x1 - x0, 2 * KERB, 0.2), ((x0 + x1) / 2, 0, -0.08), surface("asphalt", 0.9), coll=coll)
    for side in (-1, 1):
        box(f"pavement.{side}", (x1 - x0, FRONT - KERB, 0.24), ((x0 + x1) / 2, side * (KERB + FRONT) / 2, 0.0),
            surface("pavement", 0.9), coll=coll)
        box(f"kerb.{side}", (x1 - x0, 0.2, 0.26), ((x0 + x1) / 2, side * KERB, 0.0), surface("kerb", 0.9), coll=coll)
    sx0, sx1, sy0, sy1 = SQUARE
    box("square", (sx1 - sx0, sy1 - sy0, 0.24), ((sx0 + sx1) / 2, (sy0 + sy1) / 2, 0.0), surface("paving", 0.9), coll=coll)
    px0, px1 = PLAZA
    box("plaza", (px1 - px0, 34.5, 0.22), (0, -9 - 34.5 / 2, 0.0), surface("paving", 0.9), coll=coll)
    verts, faces = [], []
    for x in range(int(x0), int(x1), 6):  # centre line: 3 m dashes every 6 m
        i = len(verts)
        verts += [(x, -0.07, 0.025), (x + 3, -0.07, 0.025), (x + 3, 0.07, 0.025), (x, 0.07, 0.025)]
        faces.append((i, i + 1, i + 2, i + 3))
    for side in (-1, 1):  # parking lane lines
        i = len(verts)
        y = side * 3.5
        verts += [(x0, y - 0.06, 0.025), (x1, y - 0.06, 0.025), (x1, y + 0.06, 0.025), (x0, y + 0.06, 0.025)]
        faces.append((i, i + 1, i + 2, i + 3))
    mesh_object("markings", verts, faces, surface("marking", 0.8), coll=coll)
    for name in ("ground", "road", "pavement.-1", "pavement.1", "kerb.-1", "kerb.1", "square", "plaza", "markings"):
        bpy.data.objects[name]["sfx_occluder"] = False


def _rows(rnd: random.Random, lit: float, coll, side_street: bool = False) -> None:
    walls = ["wall_1", "wall_2", "wall_3", "wall_4", "wall_5"]
    n = 0

    def row(x_from: float, x_to: float, place) -> None:
        nonlocal n
        x = x_from
        while x < x_to - 6:
            w = min(rnd.uniform(9, 15), x_to - x)
            h = rnd.choice([7.5, 9.0, 10.5, 12.0])
            d = rnd.uniform(9, 12)
            hs = models.house(f"house.{n}", w, d, h, rnd.choice(walls), lit=lit, seed=n,
                              roof=rnd.choice(["roof", "roof_dark"]), coll=coll)
            place(hs, x + w / 2)
            n += 1
            x += w + (4.0 if rnd.random() < 0.15 else 0.0)

    def north(h, x):
        h.location = (x, FRONT, 0)

    def south(h, x):
        h.location = (x, -FRONT, 0)
        h.rotation_euler = (0, 0, math.pi)

    sx0, sx1, sy0, sy1 = SQUARE
    row(STREET[0], sx0, north)
    row(sx1, STREET[1], north)
    row(STREET[0], PLAZA[0], south)
    row(PLAZA[1], STREET[1], south)
    row(sx0, sx1, lambda h, x: setattr(h, "location", (x, sy1, 0)))

    def west(h, y):
        h.location = (sx0, y, 0)
        h.rotation_euler = (0, 0, math.pi / 2)

    def east(h, y):
        h.location = (sx1, y, 0)
        h.rotation_euler = (0, 0, -math.pi / 2)

    row(sy0 + 2, sy1, west)
    if side_street:  # the east side in two parts, with the side street's mouth between them
        row(sy0 + 2, SIDE_Y - SIDE_HALF, east)
        row(SIDE_Y + SIDE_HALF, sy1, east)
    else:
        row(sy0 + 2, sy1, east)


def _side_street(rnd: random.Random, lit: float, coll) -> None:
    """The side street's paving and its two rows of houses, from behind the square's east row (whose
    houses are at most 12 m deep) to SIDE_END."""
    x0 = SQUARE[1]
    box("side_street", (SIDE_END - x0 + 2, 2 * SIDE_HALF, 0.24), ((x0 + SIDE_END) / 2, SIDE_Y, 0.0),
        surface("paving", 0.9), coll=coll)
    bpy.data.objects["side_street"]["sfx_occluder"] = False
    walls = ["wall_1", "wall_2", "wall_3", "wall_4", "wall_5"]
    for side in (-1, 1):
        x, n = x0 + 12.5, 0
        while x < SIDE_END - 6:
            w = min(rnd.uniform(8, 13), SIDE_END - x)
            h = rnd.choice([7.5, 9.0, 10.5])
            hs = models.house(f"side.{side}.{n}", w, rnd.uniform(9, 11), h, rnd.choice(walls), lit=lit,
                              seed=100 + 10 * n + side, roof=rnd.choice(["roof", "roof_dark"]), coll=coll)
            hs.location = (x + w / 2, SIDE_Y + side * SIDE_HALF, 0)
            if side < 0:
                hs.rotation_euler = (0, 0, math.pi)  # the front towards the street (+Y)
            n += 1
            x += w
