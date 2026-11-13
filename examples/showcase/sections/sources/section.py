"""Storyboard of ``sources`` (README.md): one line per sound, added one pass at a time."""

from kit.story import Pass, Section, TitlePage

SECTION = Section(
    key="sources",
    title="One line per sound",
    title_page=TitlePage(
        title="One line per sound",
        claim="A sound is one line in the script that builds the scene: a sample, on an object.",
        code='tag.add_sound(car, "car_engine.wav")',
        listen="each line adding one sound, at the place of its object.",
    ),
    passes=(
        Pass("loop", 180, "A loop on an object"),
        Pass("layers", 180, "More sounds on the same object"),
        Pass("events", 270, "One-shots on frames"),
        Pass("bed", 150, "A bed that does not move"),
        Pass("pitch", 210, "One sample, three vehicles"),
        Pass("stems", 180, "Groups become stems"),
    ),
    gain_db=4.5,
)

CAMERA = (0.0, 13.75)
"""Where the main camera stands on the square: 12 m from the lane the car drives in."""
PITCH_CAMERA = (0.0, 40.0)
SPEED = 30 / 3.6
"""The car, m/s (30 km/h)."""
CAR_MIDDLE_S = 3.0
"""The car passes the middle of the frame 3 s into ``loop`` and ``layers``."""
HORN_FRAME = 331
BELL_FRAMES = (466, 526, 586)
STEMS_BELL_S = 0.5
STEMS_MIDDLE_S = 2.0
IDLE_X = -2.0
PAN_S = (1.0, 4.0)
PITCH = {"scooter": (1.6, 4.2), "car": (1.0, 0.0), "truck": (0.6, -4.8)}
"""Vehicle: (pitch, x on the square); they stand ``PITCH_DISTANCE`` in front of the pitch camera."""
PITCH_DISTANCE = 12.0
PITCH_ALONE_S = {"scooter": (0.1, 1.9), "car": (1.9, 3.7), "truck": (3.7, 5.5)}
PITCH_TOGETHER_S = (5.5, 6.6)
