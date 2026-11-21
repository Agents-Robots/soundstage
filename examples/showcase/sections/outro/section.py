"""Storyboard of ``outro`` (README.md): the end card over a town at night, with fireworks bursting
behind it whose bangs arrive late."""

import math

from kit.story import REPO_URL, Pass, Section

SECTION = Section(
    key="outro",
    title="End card",
    title_frames=0,
    passes=(Pass("card", 420, ""),),
    reverb="city_streets",
    gain_db=4.5,
    loudness_reported_only=True,
)
TAGLINE = "Offline spatial sound for Blender animations"
STEPS = (
    ("tag", 'tag.add_sound(car, "engine.wav")'),
    ("bake", "soundstage bake scene.blend --out bake/"),
    ("render", "soundstage render bake/scene.json -o mix.wav"),
)
STATEMENT = "Every sound in this video was rendered by SoundStage from the Blender scenes shown."
WHERE = REPO_URL.removeprefix("https://")
INSTALL = f"pip install git+{REPO_URL}"
ALSO = ("Stems per group", "loudness normalization", "true-peak limiter", "solo and mute",
        "reverb presets and impulse responses")
SEPARATOR = " · "
NO_RECORDINGS = "All sounds synthesized"

C = 343.0
BURSTS = (
    # (seconds from the start, distance m, azimuth deg right of the view, height m, colour, sample)
    (1.6, 480.0, 22.0, 150.0, "spark_gold", "firework_bang_1.wav"),
    (4.0, 560.0, 27.0, 195.0, "spark_red", "firework_bang_2.wav"),
    (6.4, 520.0, 20.0, 125.0, "spark_blue", "firework_bang_3.wav"),
    (8.6, 600.0, 25.0, 215.0, "spark_gold", "firework_bang_1.wav"),
)
"""Bursts to the right of the text column; each bang arrives 1.4 to 1.9 s after its flash."""
RISE_S = 1.2
BED_DB = -22.0
BED_S = (0.3, 11.8)
"""The town's night bed (non-spatial): fades in over 1.5 s from 0.3 s, and out over 1.5 s from 11.8 s, so that
the last 0.2 s are silent (C5)."""


def burst_at(distance: float, azimuth_deg: float, height: float) -> tuple[float, float, float]:
    """Position of a burst seen from the camera at the origin looking along +Y."""
    a = math.radians(azimuth_deg)
    return (distance * math.sin(a), distance * math.cos(a), height)


def heard_s(i: int) -> float:
    t, d, az, h, *_ = BURSTS[i]
    return t + math.dist((0.0, 0.0, 1.6), burst_at(d, az, h)) / C


def credits(*tomls: str) -> str:
    """The credits line from the text of sounds/sources.toml and sounds/animations.toml: the recordings'
    authors in order of first appearance (R3)."""
    import tomllib
    authors = []
    for text in tomls:
        for r in tomllib.loads(text).get("recording", []):
            if r["author"] not in authors:
                authors.append(r["author"])
    if not authors:
        return NO_RECORDINGS
    return "Recorded sounds: " + ", ".join(authors) + "; all other sounds synthesized"
