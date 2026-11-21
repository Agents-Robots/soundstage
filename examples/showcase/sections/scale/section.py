"""Storyboard of ``scale`` (README.md): a queue of forty instanced cars with one loop phase, then
with one each; a motorway of 300 instanced vehicles, 600 sources."""

import hashlib
import math
import random

from kit.story import FPS, Pass, Section, TitlePage

SECTION = Section(
    key="scale",
    title="Many sources",
    title_page=TitlePage(
        title="Many sources",
        claim="Instanced objects carry their sounds along. Hundreds of sources render in full where they matter.",
        code="instance_limit = 0   detail_voices = 64   cull_db = -40",
        listen="forty engines, not one; and a motorway that sounds like one.",
    ),
    passes=(
        Pass("same", 210, "40 cars, the same loop from the same point", "loop_phase=0"),
        Pass("random", 210, "40 cars, each at its own point of the loop", 'loop_phase="random"'),
        Pass("motorway", 600, "300 vehicles, 600 sources", 'instance_limit=0  quality="high"',
             settings={"quality": "high"}),
    ),
    gain_db=1.5,
    reference="motorway",
    # check.py: what the default instance_limit keeps of the queue
    bakes={"default_limit": {"instance_limit": 32, "frames": "91-510"}},
)
INSTANCE_LIMIT = 0
"""Every instance is a source (the default keeps the 32 closest per tagged object)."""
FADE_IN_S = 0.3
QUEUE_END_S = 5.75
"""The queue's loops end here and fade out over 0.3 s: the farthest car (228 m) is heard 0.66 s later,
0.3 s before the pass ends (S3)."""

# --- queue ---------------------------------------------------------------------------------------------

QUEUE = 40
QUEUE_GAP = 6.0
"""Cars along +X from x = 0, facing +X (towards the front of the queue), 6 m apart."""
QUEUE_ENGINE = (1.5, 0.0, 0.5)
"""The engine relative to a car's origin on the ground: under the bonnet."""
WALK = ((-4.0, -2.5), (6.5, -2.5))
"""The camera walks 10.5 m in 7 s, 2.5 m beside the cars, looking along the queue."""
IDLE_SECONDS = 12.0
"""Length of ``car_idle.wav``: its loop period (``loop_crossfade=0``)."""


def queue_x(i: int) -> float:
    return i * QUEUE_GAP


def camera_queue(t: float) -> tuple[float, float, float]:
    (x0, y0), (x1, y1) = WALK
    u = min(max(t / 7.0, 0.0), 1.0)
    return (x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, 1.6)


def loop_phase_s(source_id: str, period_s: float, rate: int = 48000) -> float:
    """Where the engine starts a ``loop_phase="random"`` loop (soundstage.engine.signals): a seeded
    integer below the period in samples; numpy is only needed for that draw."""
    import numpy as np
    seed = int.from_bytes(hashlib.sha256(source_id.encode()).digest()[:8], "little")
    return int(np.random.default_rng(seed).integers(0, int(period_s * rate))) / rate


# --- motorway ------------------------------------------------------------------------------------------
# Along X, 4 km; carriageway +X at y = -5.5 and -9 (inner, outer lane), carriageway -X at y = 5.5 and 9.
# The bridge crosses it at x = 0.

ROAD = (-2000.0, 2000.0)
LANES = {"east_1": (-9.0, 1), "east_2": (-5.5, 1), "west_2": (5.5, -1), "west_1": (9.0, -1)}
"""Lane: (y, direction); ``_1`` is the outer lane (trucks and slower cars), ``_2`` the inner one."""
VARIANTS = {
    # name: (kind, pitch, km/h range)
    "car_a": ("car", 0.9, (110, 130)), "car_b": ("car", 1.0, (110, 130)), "car_c": ("car", 1.1, (110, 130)),
    "car_d": ("car", 1.2, (110, 130)), "truck_a": ("truck", 0.55, (80, 90)), "truck_b": ("truck", 0.65, (80, 90)),
}
CARS, TRUCKS = 240, 60
MOTORWAY_S = 20.0
DRONE = ((-60.0, -200.0, 60.0), (-60.0, -7.0, 12.0))
"""The drone flies from 200 m beside the motorway and 60 m up to 12 m above the outer eastbound
lane, 60 m before the bridge, eased at both ends (about 10 m/s in the middle); it looks along the
eastbound traffic, towards the bridge."""
BRIDGE_Z = 6.0


def drone(t: float) -> tuple[float, float, float]:
    u = min(max(t / MOTORWAY_S, 0.0), 1.0)
    u = u * u * (3 - 2 * u)
    (x0, y0, z0), (x1, y1, z1) = DRONE
    return (x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, z0 + (z1 - z0) * u)


def traffic(seed: int = 7) -> list[dict]:
    """The 300 vehicles: variant, lane, x at the start of the pass, speed (m/s). In each lane the
    vehicles are ordered so that every one is at least as fast as the one behind it: nobody catches
    up, no two overlap (R5)."""
    rnd = random.Random(seed)
    kinds = ["truck_a", "truck_b"] * (TRUCKS // 2) + [f"car_{c}" for c in "abcd"] * (CARS // 4)
    rnd.shuffle(kinds)
    trucks = [k for k in kinds if k.startswith("truck")]
    cars = [k for k in kinds if k.startswith("car")]
    lanes = {"east_1": trucks[:30] + cars[:45], "west_1": trucks[30:] + cars[45:90],
             "east_2": cars[90:165], "west_2": cars[165:]}
    out = []
    span = ROAD[1] - ROAD[0]
    for lane, members in lanes.items():
        y, direction = LANES[lane]
        rnd.shuffle(members)
        speeds = sorted(rnd.uniform(*VARIANTS[v][2]) / 3.6 for v in members)
        gap = span / len(members)
        for i, (variant, v) in enumerate(zip(members, speeds)):
            # i = 0 is the rearmost; the front is reached last: speeds rise towards the front
            s = ROAD[0] + gap * (i + rnd.uniform(0.2, 0.8))
            x = s if direction > 0 else -s
            out.append({"variant": variant, "lane": lane, "x0": x, "speed": v * direction, "y": y})
    return out


def min_gap(vehicles: list[dict], seconds: float = MOTORWAY_S) -> float:
    """Smallest distance between two vehicles of one lane during the pass (front to front)."""
    worst = math.inf
    for lane in LANES:
        mine = [v for v in vehicles if v["lane"] == lane]
        for t in (0.0, seconds):
            xs = sorted(v["x0"] + v["speed"] * t for v in mine)
            worst = min(worst, min(b - a for a, b in zip(xs, xs[1:])))
    return worst


def frames_motorway() -> int:
    return round(MOTORWAY_S * FPS)


C = 343.0
HEARD_BY_S = MOTORWAY_S - 0.3
"""Every vehicle's sound has reached the drone by then (S3)."""
BANDS = ((250.0, 0.5), (700.0, 1.0), (1400.0, 2.0), (None, 3.0))
"""Distance bands (upper edge in metres, fade-out in seconds): a vehicle's loops end so that their
faded end, emitted from up to the band's edge, reaches the drone by HEARD_BY_S. The farther the
band, the earlier and the longer the fade, so the distant wash thins out instead of stopping."""


def end_distance(v: dict) -> float:
    """Largest distance from the vehicle to the drone's last position over the pass's second half."""
    end = drone(MOTORWAY_S)
    return max(math.dist((v["x0"] + v["speed"] * t, v["y"], 0.5), end) for t in (MOTORWAY_S / 2, MOTORWAY_S))


def band_of(v: dict) -> int:
    d = end_distance(v)
    return next(i for i, (edge, _) in enumerate(BANDS) if edge is None or d <= edge)


def band_end_s(i: int, vehicles: list[dict]) -> float:
    """When the loops of band i end (s into the pass); they fade out over the band's fade after it."""
    edge, fade = BANDS[i]
    if edge is None:
        edge = max(end_distance(v) for v in vehicles if band_of(v) == i)
    return HEARD_BY_S - fade - edge / C
