"""Storyboard of ``intro`` (README.md): one street shot, first silent, then with its sound."""

from kit.story import Pass, Section

SECTION = Section(
    key="intro",
    title="SoundStage",
    title_frames=0,
    passes=(
        Pass("silent", 195, "Blender renders the picture."),
        Pass("sound", 345, "SoundStage renders the sound."),
    ),
    reverb="city_streets",
    gain_db=-2.0,
)

TAGLINE = "Sound for Blender animations, computed from the scene."
NOTE = "Headphones recommended."
CAMERA_X = 110.0
"""Where the shot stands along the main street (town coordinates)."""
SPEED = 20.0
"""Ambulance, m/s (72 km/h)."""
PASS_AT_S = 4.5
CAR_SPEED = 40 / 3.6
CAR_PASS_AT_S = 2.0
WORDMARK_FRAME = 421
SOURCES_END_FRAME = 480
