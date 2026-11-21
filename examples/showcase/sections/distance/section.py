"""Storyboard of ``distance`` (README.md): an open-air stage heard from five cameras, each half as
far away as the one before."""

import math

from kit.story import Pass, Section, TitlePage

SECTION = Section(
    key="distance",
    title="Distance",
    title_page=TitlePage(
        title="Distance",
        claim="Sound gets quieter with distance, and duller: air absorbs the high frequencies first.",
        code='distance_model = "inverse_clamped"   air_absorption = 1.0',
        listen="the level at each camera position, and the hi-hats that only arrive close up.",
    ),
    passes=(
        Pass("none", 375, "No distance model", 'distance_model="none"  air_absorption=0'),
        Pass("inverse", 375, "Inverse distance law: −6 dB per doubling", 'distance_model="inverse_clamped"  air_absorption=0'),
        Pass("air", 375, "Distance law and air absorption", 'distance_model="inverse_clamped"  air_absorption=1'),
    ),
    gain_db=4.0,
)

DISTANCES = (686.0, 343.0, 171.5, 85.75, 42.875)
"""Camera to music source (m), in the order of the shots: 2 s, 1 s, 1/2 s, 1/4 s, 1/8 s of travel."""
SHOT_FRAMES = 75
SOURCE_Z = 4.0
"""The music: middle of the stage front, 4 m up."""
CAMERA_Z = 3.0
LENS = 50.0
LEAD_FRAMES = 75
"""The music starts this long before its pass (R4)."""
END_S = 0.35
"""The music has faded out this long before its pass ends; the nearest camera hears the end 0.125 s
later, so the last 0.225 s of a pass are silent (C5 asks for 0.2 s at the section's end)."""
FADE_OUT_S = 0.4
REF_DISTANCE = DISTANCES[-1]
PASS_SOURCE = {
    "none": {"distance_model": "none", "air_absorption": 0.0},
    "inverse": {"distance_model": "inverse_clamped", "air_absorption": 0.0},
    "air": {},
}
"""Per-source keys of each pass; ``air`` runs at the defaults."""
BANDS_HZ = (125, 250, 500, 1000, 2000, 4000, 8000, 16000)
"""The spectrum strip in ``air``."""


def camera_y(d: float) -> float:
    """Y of the camera whose distance to the music source is d (the stage front is at y = 0)."""
    return -math.sqrt(d * d - (SOURCE_Z - CAMERA_Z) ** 2)


def level_db(d: float) -> float:
    """Inverse distance law, clamped at the reference distance."""
    return 20 * math.log10(min(1.0, REF_DISTANCE / d))


def air_alpha_db_per_m(f: float, temperature_c: float = 20.0, humidity_pct: float = 50.0) -> float:
    """ISO 9613-1 pure-tone attenuation (dB/m) at standard pressure, for the instruments. The check
    compares it with the engine's ``soundstage.engine.filters.iso9613_alpha``."""
    t = temperature_c + 273.15
    t0, t01 = 293.15, 273.16
    h = humidity_pct * 10.0 ** (-6.8346 * (t01 / t) ** 1.261 + 4.6151)
    fr_o = 24.0 + 4.04e4 * h * (0.02 + h) / (0.391 + h)
    fr_n = (t / t0) ** -0.5 * (9.0 + 280.0 * h * math.exp(-4.170 * ((t / t0) ** (-1 / 3) - 1.0)))
    return 8.686 * f * f * (1.84e-11 * (t / t0) ** 0.5 + (t / t0) ** -2.5 * (
        0.01275 * math.exp(-2239.1 / t) / (fr_o + f * f / fr_o) + 0.1068 * math.exp(-3352.0 / t) / (fr_n + f * f / fr_n)))
