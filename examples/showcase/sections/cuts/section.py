"""Storyboard of ``cuts`` (README.md): three race cars on an oval covered by five cameras in six
shots, heard from one fixed microphone, then with the sound cutting with the picture."""

import math

from kit.story import FPS, Pass, Section, TitlePage

HIGH = {"quality": "high"}
SECTION = Section(
    key="cuts",
    title="Camera cuts",
    title_page=TitlePage(
        title="Camera cuts",
        claim="The camera is the microphone. When the picture cuts, level, direction, delay and pitch cut with it.",
        code="marker.camera = camera_2",
        listen="each shot having its own sound, most of all on board.",
    ),
    passes=(
        Pass("one_mic", 450, "Five cameras, one microphone", 'listener="cuts.cam_a"', "WITHOUT", settings=HIGH,
             bake="one_mic"),
        Pass("per_camera", 450, "Five cameras, the sound cuts with the picture", "listener: the active camera", "WITH",
             settings=HIGH),
    ),
    gain_db=1.0,
    bakes={"one_mic": {"listener": "cuts.cam_a"},
           # check.py: what each camera alone hears through the second pass
           **{f"cam_{n}": {"listener": f"cuts.cam_{n}", "frames": "541-990"} for n in "abcde"}},
)
C = 343.0

# --- the oval ----------------------------------------------------------------------------------------
# The start straight runs along +X on y = 0 from x = 0 to 250; turn 1 is a half circle of 80 m about
# (250, 80); the back straight runs back along y = 160; turn 2 about (0, 80). The cars drive
# counter-clockwise seen from above. s is the distance along the cars' line from the start line.

STRAIGHT = 250.0
TURN_R = 80.0
LAP = 2 * STRAIGHT + 2 * math.pi * TURN_R
SPEED = 50.0
"""180 km/h."""
LEAD_S0 = 25.0
GAP_M = 60.0
CARS = 3
RACE_PITCH = 1.8
"""``race_engine.wav`` is a large car's engine at 100 Hz firing; raised to a racing engine's."""
ENGINE_Z = 0.5


def track_point(s: float) -> tuple[float, float, float]:
    """(x, y, heading) of the line at s; heading in radians, counter-clockwise from +X."""
    s %= LAP
    half = math.pi * TURN_R
    if s < STRAIGHT:
        return (s, 0.0, 0.0)
    s -= STRAIGHT
    if s < half:
        a = -math.pi / 2 + s / TURN_R
        return (STRAIGHT + TURN_R * math.cos(a), TURN_R + TURN_R * math.sin(a), a + math.pi / 2)
    s -= half
    if s < STRAIGHT:
        return (STRAIGHT - s, 2 * TURN_R, math.pi)
    s -= STRAIGHT
    a = math.pi / 2 + s / TURN_R
    return (TURN_R * math.cos(a), TURN_R + TURN_R * math.sin(a), a + math.pi / 2)


def car_s(k: int, t: float) -> float:
    """Distance along the line of car k (0 = the lead car) t seconds into a pass."""
    return LEAD_S0 + SPEED * t - GAP_M * k


def outward(s: float, d: float, z: float) -> tuple[float, float, float]:
    """A point d metres outside the line at s (to the right of the cars), z high."""
    x, y, h = track_point(s)
    return (x + d * math.sin(h), y - d * math.cos(h), z)


SHOT_S = 2.5
SHOTS = ("a", "b", "c", "d", "b", "e")
CAMERAS = {
    # name: (place in words, lens mm)
    "a": ("trackside", 28.0),
    "b": ("on board", 20.0),
    "c": ("turn 1", 35.0),
    "d": ("grandstand", 24.0),
    "e": ("back straight", 24.0),
}
CAM_A = outward(70.0, 12.0, 1.5)
CAM_C = outward(320.0, 20.0, 3.0)
CAM_D = (STRAIGHT, 2 * TURN_R + 110.0, 30.0)
"""On the grandstand's roof outside the back straight, where turn 1 ends."""
CAM_E = outward(675.0, 6.0, 0.5)
ON_BOARD = (0.0, 0.55, 1.35)
"""Camera B relative to the lead car (above and behind the driver's helmet; the car faces -Y)."""
SHOT_FRAMES = round(SHOT_S * FPS)


def shot_at(t: float) -> int:
    return min(int(t // SHOT_S), len(SHOTS) - 1)


def camera_position(name: str, t: float) -> tuple[float, float, float]:
    """World position of camera ``name`` t seconds into a pass (B rides on the lead car)."""
    if name == "b":
        x, y, h = track_point(car_s(0, t))
        # the car's -Y is its front: local (0, 0.55) is 0.55 m behind its middle
        return (x - ON_BOARD[1] * math.cos(h), y - ON_BOARD[1] * math.sin(h), ON_BOARD[2])
    return {"a": CAM_A, "c": CAM_C, "d": CAM_D, "e": CAM_E}[name]


def lead_distance(name: str, t: float) -> float:
    x, y, _ = track_point(car_s(0, t))
    return math.dist((x, y, ENGINE_Z), camera_position(name, t))
