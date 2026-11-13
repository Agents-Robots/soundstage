"""Storyboard of ``reverb`` (README.md): a figure bouncing a basketball and clapping in four spaces,
then walking away from the camera down a church nave."""

import math

from kit.story import Pass, Section, TitlePage

SECTION = Section(
    key="reverb",
    title="Reverb",
    title_page=TitlePage(
        title="Reverb",
        claim="The same sound in four spaces. The reverberation stays as a source walks away, the direct sound does not.",
        code='reverb = "chapel"',
        listen="the tail after each clap, and how the steps sink into the room.",
    ),
    passes=(
        Pass("outdoors", 150, "Outdoors", "no reverb"),
        Pass("livingroom", 150, "Living room, 0.5 s", 'reverb="livingroom"', settings={"reverb": "livingroom"}),
        Pass("gym", 210, "Gym, 3.1 s", 'reverb="sport_gymnasium"', settings={"reverb": "sport_gymnasium"}),
        Pass("church", 240, "Church, 4.6 s", 'reverb="chapel"', settings={"reverb": "chapel"}),
        Pass("walk", 480, "Walking away: the room stays", 'reverb="chapel"', settings={"reverb": "chapel"}),
    ),
    gain_db=6.0,
    loudness_reported_only=True,
)
ROOMS = ("outdoors", "livingroom", "gym", "church")
DECAY_S = {"livingroom": 0.50, "gym": 3.14, "church": 4.62, "walk": 4.62}
"""Mid-frequency decay time of each pass's preset (``soundstage presets``)."""
C = 343.0

CAMERA_Z = 1.6
LENS = 20.0
DISTANCE = 4.0
"""The figure stands 4 m in front of the camera, which looks along +Y from its set's origin: at 20 mm
the frame shows the room around it."""
REF_DISTANCE = 3.0
"""Inside it the distance law is clamped: every probe stays farther away (hands 3.5 m, floor 4 m)."""
AIM_Z = 1.1
"""Where the camera is aimed, above the figure's middle: the floor at its feet and the room above."""
BOUNCES_S = (0.5, 1.1, 1.7)
CLAPS_S = (2.5, 3.0)
HANDS = (0.0, -0.53, 1.28)
"""Where the hands meet in a clap (arms 72 degrees forward, 27 degrees in), relative to the figure's
origin, before it is turned (the figure faces -Y, the camera)."""
FLOOR = (0.32, -0.42, 0.0)
"""Where the ball hits the floor, relative to the figure (at its right hand)."""
BALL_R = 0.12

WALK_CLAPS_S = (0.3, 10.5)
WALK_START_S = 0.8
STEPS = 18
STEP_M = 0.7
STEP_S = 0.5
"""18 steps of 0.7 m, one every 0.5 s: the feet land from 1.3 s to 9.8 s."""
WALK_END = DISTANCE + STEPS * STEP_M
TURN_S = 0.35


def steps_s() -> list[float]:
    return [WALK_START_S + STEP_S * (i + 1) for i in range(STEPS)]


def walk_y(t: float) -> float:
    """The figure's distance from the camera t seconds into ``walk``."""
    a, b = WALK_START_S, WALK_START_S + STEPS * STEP_S
    return DISTANCE + (WALK_END - DISTANCE) * min(max((t - a) / (b - a), 0.0), 1.0)


def send_db(d: float, decay_s: float) -> float:
    """The revised send law within R (signal-model.md, "Reverb send"): the reverberation a source
    excites at d, in dB."""
    return -60.0 * d / (C * decay_s)


def direct_db(d: float) -> float:
    return 20 * math.log10(DISTANCE / d)


def hand_distance(y: float) -> float:
    """Camera to the hands of a figure standing y metres ahead, facing the camera."""
    return math.dist((0.0, 0.0, CAMERA_Z), (HANDS[0], y + HANDS[1], HANDS[2]))
