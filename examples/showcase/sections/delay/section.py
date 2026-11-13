"""Storyboard of ``delay`` (README.md): a carpenter, fireworks and lightning across a lake, heard
late by their distance, then synced to the picture."""

import math

from kit.story import Pass, Section, TitlePage

SECTION = Section(
    key="delay",
    title="Speed of sound",
    title_page=TitlePage(
        title="Speed of sound",
        claim="Sound travels at 343 m/s: three seconds per kilometre. Every source is delayed by its distance.",
        code="sync_to_picture = False",
        listen="the gap between seeing and hearing; then the same events put on their frames.",
    ),
    passes=(
        Pass("physical", 480, "Sound travels at 343 m/s", "sync_to_picture=False"),
        Pass("synced", 480, "Synced to the picture", "sync_to_picture=True"),
    ),
    gain_db=10.5,
)

CAMERA = (0.0, 0.0, 1.6)
"""Both cameras stand here, on the near shore."""
SYNC = {"physical": False, "synced": True}

HAMMER_S = (0.4, 1.2, 2.0)
CUT_S = 2.9
"""Cut from the 300 mm lens (the carpenter) to the 28 mm lens (fireworks and lightning)."""
BURSTS_S = (3.2, 4.4, 5.6)
LIGHTNING_S = 8.0


def place(distance: float, azimuth_deg: float, height: float) -> tuple[float, float, float]:
    """A point ``distance`` from the camera, ``azimuth_deg`` to the right of straight ahead (+Y), at
    ``height`` above the ground."""
    dz = height - CAMERA[2]
    horizontal = math.sqrt(distance ** 2 - dz ** 2)
    a = math.radians(azimuth_deg)
    return (CAMERA[0] + horizontal * math.sin(a), CAMERA[1] + horizontal * math.cos(a), height)


EVENTS = {
    # name: (distance m, azimuth deg, height m, sample(s), ref_distance, times s from the pass start)
    "hammer": (171.5, -8.5, 1.35, "hammer_hit.wav", 100.0, HAMMER_S),
    "burst_1": (514.5, 20.0, 110.0, "firework_bang_1.wav", 250.0, (BURSTS_S[0],)),
    "burst_2": (686.0, 9.0, 150.0, "firework_bang_2.wav", 250.0, (BURSTS_S[1],)),
    "burst_3": (514.5, 29.0, 95.0, "firework_bang_3.wav", 250.0, (BURSTS_S[2],)),
    "lightning": (1029.0, -3.0, 250.0, "thunder.wav", 400.0, (LIGHTNING_S,)),
}
PAD_SECONDS = 4.0
"""Bake padding: the default 3 s covers 1029 m without margin."""
