"""Storyboard of ``city`` (README.md): ten thousand cars in a city grid at blue hour, each with an
engine and tyres; a drone comes down from 600 m to the median of the boulevard."""

import math
import random

from kit.story import FPS, Pass, Section, TitlePage

CARS = 10_000
SOURCES = 2 * CARS
RENDER_CLAIM_MIN = 6
"""The callout says the sound of the pass rendered in under this many minutes on one 16-core CPU;
check.py asserts it against the render time in the section's report (R7)."""

SECTION = Section(
    key="city",
    title="Ten thousand cars",
    title_page=TitlePage(
        title="Ten thousand cars",
        claim="Every car has its own engine and tyres: the near ones in full detail, the rest in one "
              "physical far field.",
        code="detail_voices = 64   cull_db = -40",
        listen="a whole city from above, turning into single cars passing by.",
    ),
    passes=(
        Pass("night", 900, f"Each car an engine and tyres: {SOURCES:,} sources".replace(",", " "), "default settings"),
    ),
    gain_db=-7.0,
)
PAD_S = 6.0
"""Bake padding: sound from the farthest car (2.6 km, 7.6 s) that is heard at the pass's first frame
was emitted before the timeline starts (title page 3 s)."""
PASS_S = 30.0

# --- the city ------------------------------------------------------------------------------------------
# A grid of blocks around the origin. The boulevard runs along X at y = 0; avenues along X every
# BLOCK m; streets along Y every BLOCK m. Traffic drives on the right.

BLOCK = 120.0
GRID = 10
"""Avenues and streets at -GRID..GRID times BLOCK: the city is 2.4 km across."""
EXTENT = 1800.0
"""Lanes run on to +-EXTENT beyond the city, into the dark land around it."""
BOULEVARD_HALF = 13.0
AVENUE_HALF = 8.0
STREET_HALF = 5.0
QUIET_STREETS = 4
"""Streets with |j| <= QUIET_STREETS carry no traffic: their cars would cross the boulevard's
traffic where the camera stands (vehicles do not stop at junctions)."""

LANES = {
    # kind: (lane offsets from the road's centre line, m; speed range km/h; mean gap m)
    "boulevard": ((3.75, 7.25, 10.75), (60, 80), 24.0),
    "avenue": ((2.25, 5.75), (45, 60), 32.0),
    "street": ((2.25,), (30, 45), 40.0),
}
VARIANTS = {
    # name: (kind, paint, pitch)
    "car_a": ("car", "car_red", 0.9), "car_b": ("car", "car_blue", 1.0), "car_c": ("car", "car_grey", 1.1),
    "car_d": ("car", "white", 1.2), "truck_a": ("truck", "truck_box", 0.55), "truck_b": ("truck", "car_red", 0.65),
}
TRUCK_SHARE = 0.08


def roads() -> list[tuple[str, str, float]]:
    """(kind, axis, offset): roads along ``axis`` ("x" or "y") at ``offset`` on the other axis."""
    out = [("boulevard", "x", 0.0)]
    out += [("avenue", "x", k * BLOCK) for k in range(-GRID, GRID + 1) if k]
    out += [("street", "y", j * BLOCK) for j in range(-GRID, GRID + 1) if abs(j) > QUIET_STREETS]
    return out


def traffic(seed: int = 11) -> list[dict]:
    """The vehicles: variant, axis, lane position, start position along the road, speed (m/s, signed).
    In each lane every vehicle is at least as fast as the one behind it, so nobody catches up.
    The counts per lane follow the lane's mean gap, scaled to CARS in all."""
    rnd = random.Random(seed)
    lanes = []
    for kind, axis, offset in roads():
        offsets, speeds, gap = LANES[kind]
        for d in offsets:
            for direction in (1, -1):
                # right-hand traffic: along +X on the -Y side, along +Y on the +X side
                side = -direction if axis == "x" else direction
                lanes.append((kind, axis, offset + side * d, direction, speeds, gap))
    weight = [2 * EXTENT / gap for *_, gap in lanes]
    scale = CARS / sum(weight)
    counts = [int(w * scale) for w in weight]
    for i in rnd.sample(range(len(lanes)), CARS - sum(counts)):
        counts[i] += 1
    out = []
    for (kind, axis, across, direction, (v0, v1), _), n in zip(lanes, counts):
        speeds = sorted(rnd.uniform(v0, v1) / 3.6 for _ in range(n))
        span = 2 * EXTENT / n
        for i, v in enumerate(speeds):
            # i = 0 is the rearmost: speeds rise towards the front
            s = -EXTENT + span * (i + rnd.uniform(0.25, 0.75))
            kind_v = "truck" if rnd.random() < TRUCK_SHARE else "car"
            variant = rnd.choice([k for k, (c, *_) in VARIANTS.items() if c == kind_v])
            out.append({"variant": variant, "road": kind, "axis": axis, "across": across,
                        "along0": s * direction, "speed": v * direction})
    return out


def position(v: dict, t: float) -> tuple[float, float, float]:
    along = v["along0"] + v["speed"] * t
    return (along, v["across"], 0.5) if v["axis"] == "x" else (v["across"], along, 0.5)


def min_gap(vehicles: list[dict]) -> float:
    """Smallest distance between two vehicles of one lane during the pass (front to front)."""
    lanes: dict[tuple, list] = {}
    for v in vehicles:
        lanes.setdefault((v["axis"], v["across"], v["speed"] > 0), []).append(v)
    worst = math.inf
    for members in lanes.values():
        for t in (0.0, PASS_S):
            xs = sorted(v["along0"] + v["speed"] * t for v in members)
            worst = min(worst, min((b - a for a, b in zip(xs, xs[1:])), default=math.inf))
    return worst


# --- the drone -----------------------------------------------------------------------------------------

PATH = ((-420.0, -160.0, 320.0), (-320.0, 0.0, 270.0), (-200.0, 0.0, 170.0), (-40.0, 0.0, 2.2))
"""Cubic Bezier: from 320 m up, south-west of the boulevard; it lines up over the boulevard while
still above the roofs (160 m at 12 s) and comes down between its buildings to 2.2 m above the median.
At most 29 m/s (105 km/h): a faster drone shifts the pitch of the whole city (Doppler from the
listener's motion; at 160 m/s, the first version, by up to half an octave). ``build.py`` checks that
it never enters a building."""
AIMS = ((150.0, 250.0, 0.0), (420.0, 0.0, 1.8))
"""Where the camera looks: the centre of the city at first, along the boulevard at the end."""
DESCENT_S = 26.0
"""The drone comes down in 26 s and then stands on the median for the rest of the pass."""


def _bezier(points, u: float) -> tuple[float, float, float]:
    a, b, c, d = points
    w = ((1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u ** 3)
    return tuple(sum(wi * p[k] for wi, p in zip(w, (a, b, c, d))) for k in range(3))


def progress(t: float) -> float:
    """Eased at both ends."""
    s = min(max(t / DESCENT_S, 0.0), 1.0)
    return 1.0 - (1.0 - s ** 1.4) ** 2.4


def drone(t: float) -> tuple[float, float, float]:
    return _bezier(PATH, progress(t))


def aim(t: float) -> tuple[float, float, float]:
    u = progress(t) ** 3
    (x0, y0, z0), (x1, y1, z1) = AIMS
    return (x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, z0 + (z1 - z0) * u)


# --- loop ends -----------------------------------------------------------------------------------------

C = 343.0
HEARD_BY_S = PASS_S - 0.3
BANDS = ((300.0, 0.5), (800.0, 1.0), (1600.0, 2.0), (None, 3.0))
"""Distance bands (upper edge in metres, fade-out in seconds), as in ``scale``: a vehicle's loops end
so that their faded end, emitted from up to the band's edge, reaches the camera by HEARD_BY_S."""


def end_distance(v: dict) -> float:
    """Largest distance from the vehicle to the camera's last position over the pass's second half."""
    end = drone(PASS_S)
    return max(math.dist(position(v, t), end) for t in (PASS_S / 2, PASS_S))


def band_of(v: dict) -> int:
    d = end_distance(v)
    return next(i for i, (edge, _) in enumerate(BANDS) if edge is None or d <= edge)


def band_end_s(i: int, vehicles: list[dict]) -> float:
    edge, fade = BANDS[i]
    if edge is None:
        edge = max(end_distance(v) for v in vehicles if band_of(v) == i)
    return HEARD_BY_S - fade - edge / C


def frame_of(t: float) -> float:
    return SECTION.window("night").first + t * FPS
