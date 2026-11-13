"""Storyboard of ``finale`` (README.md): one evening in the town in seven shots, one pass, one render
at default settings. Times are seconds from the start of the pass (frame 91); positions in the
town's coordinates (kit/blender/town.py)."""

import math

from kit.story import FPS, Pass, Section, TitlePage

SECTION = Section(
    key="finale",
    title="All together",
    title_page=TitlePage(
        title="All together",
        claim="One evening in a town. Every sound comes from the scene: one bake, one render, nothing mixed by hand.",
        code="soundstage render bake/scene.json -o town.wav",
        listen="where each sound is, how far away, and what stands in between.",
    ),
    passes=(Pass("town", 2250, ""),),
    reverb="city_streets",
    gain_db=3.9,
)
C = 343.0
PASS_S = 75.0

SHOTS = (("overview", 0.0), ("street", 9.0), ("corner", 20.0), ("crossing", 31.0), ("onboard", 41.0),
         ("square", 49.0), ("fireworks", 60.0))
"""Shot name and start; each runs to the next one's start, the last to the end of the pass."""


def shot_window(name: str) -> tuple[float, float]:
    starts = [s for _, s in SHOTS] + [PASS_S]
    i = [n for n, _ in SHOTS].index(name)
    return starts[i], starts[i + 1]


def frame(t: float) -> float:
    """Frame of a time in the pass."""
    return SECTION.window("town").first + t * FPS


# --- the town (kit/blender/town.py) ------------------------------------------------------------------

LANE = 1.75
FRONT = 9.0
SQUARE = (-30.0, 30.0, 9.0, 75.0)
SIDE_Y = 46.0
BELL = (-14.0, -46.25, 23.6)
"""The bell's sound: in the belfry, 0.6 m under the pivot (the church's front at (-14, -43.25) faces
the square; the pivot is 3 m behind it, 24.2 m up)."""
BELL_S = (2.0, 4.5, 7.0, 9.5)

# --- shots ---------------------------------------------------------------------------------------------

DRONE = ((-14.0, -446.0, 80.0), (-14.0, -426.0, 64.0))
"""400 m south of the church, 80 m up, sinking and closing in over the first shot (eased)."""
DRONE_AIM = (-8.0, -15.0, 12.0)
DRONE_LENS = 85.0
STREET_CAM = (6.0, 44.0, 1.6)
"""On the square, looking south across the main street (42 m away) towards the church."""
STREET_YAW, STREET_PITCH, STREET_LENS = 180.0, 4.0, 28.0
WALK_SPEED = 1.5
CORNER_X0 = 57.0
"""The camera walks down the middle of the side street towards the square (-X), from x = 57."""
CORNER_LENS = 24.0
BUSKER = (24.0, 40.0, 0.0)
"""On the square, beside the side street's mouth (x = 30, y 41.5 to 50.5)."""
BUSKER_SOUND_Z = 1.15
BUSKER_YAW = 108.0
BUSK_S = (0.2, 59.0)
"""The busker plays from the start until the first rocket rises."""
SQUARE_CAM = (5.6, 32.2, 1.6)
"""20 m from the busker, who stands 3 m left of the middle of the picture."""
SQUARE_LENS = (24.0, 70.0)
ZOOM_S = (51.0, 57.0)
FIRE_CAM = (0.0, 12.0, 1.6)
FIRE_YAW, FIRE_PITCH, FIRE_LENS = 0.0, 14.0, 24.0
CROSS_LENS, ONBOARD_LENS = 24.0, 20.0


def corner_cam(t: float) -> tuple[float, float, float]:
    u = min(max(t, 20.0), 31.0) - 20.0
    return (CORNER_X0 - WALK_SPEED * u, SIDE_Y, 1.6)


def square_yaw() -> float:
    """Compass yaw that puts the busker 3 m left of the middle at 20 m."""
    dx, dy = BUSKER[0] - SQUARE_CAM[0], BUSKER[1] - SQUARE_CAM[1]
    return math.degrees(math.atan2(-dx, dy)) - math.degrees(math.atan2(3.0, math.hypot(dx, dy)))


def square_lens(t: float) -> float:
    a, b = ZOOM_S
    u = min(max((t - a) / (b - a), 0.0), 1.0)
    return SQUARE_LENS[0] + (SQUARE_LENS[1] - SQUARE_LENS[0]) * u


# --- the ambulance -------------------------------------------------------------------------------------

AMB_SPEED = 20.0
"""72 km/h, towards -X in the lane at y = +1.75."""
AMB_PASS_S = 14.5
"""When it is in the middle of what the street camera sees of its lane through the square."""
AMB_SOUND_S = (8.0, 19.0)
SIREN_Z = 2.65


def street_opening() -> tuple[float, float]:
    """x range of the ambulance's lane seen from the street camera between the houses on both sides
    of the square's open south side (their fronts at y = 9)."""
    cx, cy, _ = STREET_CAM
    k = (cy - LANE) / (cy - FRONT)
    return cx + (SQUARE[0] - cx) * k, cx + (SQUARE[1] - cx) * k


def amb_x(t: float) -> float:
    lo, hi = street_opening()
    return (lo + hi) / 2 - AMB_SPEED * (t - AMB_PASS_S)


# --- the passer-by -------------------------------------------------------------------------------------

STEPS, STEP_M, STEP_S = 16, 0.7, 0.5
WALK_FROM_S = 21.0
PASSERBY_Y = SIDE_Y - 2.5
MEET_S = 25.0
"""The passer-by walks up the side street (+X), 2.5 m left of the camera, and passes it here."""


def passerby_x0() -> float:
    return corner_cam(MEET_S)[0] - STEP_M / STEP_S * (MEET_S - WALK_FROM_S)


# --- the railway ---------------------------------------------------------------------------------------

RAIL_Y = 140.0
"""The railway runs along X north of the town."""
RAIL_Z = 0.35
"""Tops of the rails above the ground."""
TRAIN_SPEED = 30.0
"""108 km/h, towards +X."""
XINGS = (300.0, 550.0)
FRONT_AT_XING_S = 37.0
HORN_S = 33.5
XING_BELL_S = ((29.0, 44.0), (39.0, 49.0))
TRAIN_SOUND_S = (24.0, 54.0)
"""The train's rolling: it is more than 300 m from every camera outside these times."""
XING_BELL = (3.6, -4.0, 3.0)
"""The crossing's bell from its middle (models.crossing)."""
CROSS_CAM = (XINGS[0] + 5.5, RAIL_Y - 8.0, 1.6)
CROSS_YAW = 77.0
CAB_EYE = (0.0, 1.6, 2.95)
"""The cab camera from the train's origin (the middle of its front on the rails), facing -Y."""


def train_front_x(t: float) -> float:
    return XINGS[0] + TRAIN_SPEED * (t - FRONT_AT_XING_S)


def xing_bell(i: int) -> tuple[float, float, float]:
    return (XINGS[i] + XING_BELL[0], RAIL_Y + XING_BELL[1], XING_BELL[2])


# --- the scooter ---------------------------------------------------------------------------------------

SCOOTER_SPEED = 7.0
SCOOTER_BEHIND_S = 54.0
SCOOTER_SOUND_S = (50.5, 57.5)
SCOOTER_Z = 0.6
SCOOTER_BEHIND_M = 5.0


def scooter_at(t: float) -> tuple[float, float, float]:
    """On a line across the square 5 m behind the square camera, perpendicular to its view; straight
    behind it at SCOOTER_BEHIND_S, going from the main street to the north-west."""
    yaw = math.radians(square_yaw())
    fwd = (-math.sin(yaw), math.cos(yaw))
    perp = (-fwd[1], fwd[0])
    s = SCOOTER_SPEED * (t - SCOOTER_BEHIND_S)
    if perp[1] < 0:
        perp = (-perp[0], -perp[1])
    return (SQUARE_CAM[0] - SCOOTER_BEHIND_M * fwd[0] + s * perp[0],
            SQUARE_CAM[1] - SCOOTER_BEHIND_M * fwd[1] + s * perp[1], SCOOTER_Z)


# --- fireworks -----------------------------------------------------------------------------------------

BURSTS = (
    # time s, distance m, azimuth deg (right of +Y), height m, colour
    (60.5, 520.0, -12.0, 170.0, "spark_red"),
    (61.8, 600.0, 8.0, 200.0, "spark_gold"),
    (63.0, 690.0, -22.0, 230.0, "spark_blue"),
    (64.4, 560.0, 18.0, 185.0, "spark_gold"),
    (65.6, 650.0, -4.0, 215.0, "spark_red"),
    (67.0, 500.0, 24.0, 165.0, "spark_blue"),
    (68.5, 700.0, 2.0, 240.0, "spark_gold"),
)
"""High enough that every burst clears the roofs north of the square seen from the fireworks camera,
with the Fresnel zone (R6)."""
RISE_S = 1.2


def burst_at(i: int) -> tuple[float, float, float]:
    _, d, az, h, _ = BURSTS[i]
    dz = h - FIRE_CAM[2]
    horizontal = math.sqrt(d * d - dz * dz)
    a = math.radians(az)
    return (FIRE_CAM[0] + horizontal * math.sin(a), FIRE_CAM[1] + horizontal * math.cos(a), h)


def hill_z(x: float, y: float) -> float:
    """The hill north of the town: a ridge along X, 70 m high at y = 750."""
    if not 350.0 < y < 1150.0:
        return 0.0
    return 70.0 * math.sin(math.pi * (y - 350.0) / 800.0) ** 2 * (0.85 + 0.15 * math.cos(x / 260.0))


BED_S = (0.2, 73.0)
FADE_OUT_FRAMES = 45

CALLOUTS = (
    # shot, text, from s, to s
    ("overview", "400 m away: 1.2 s late", 3.0, 6.0),
    ("street", "behind houses", 10.3, 12.6),
    ("street", "Doppler", 13.4, 16.2),
    ("corner", "around the corner", 21.5, 24.5),
    ("crossing", "Doppler", 36.4, 39.4),
    ("onboard", "the camera moves: the bell drops", 44.2, 47.2),
    ("square", "behind you", 52.6, 55.0),
    ("square", "sound follows the lens", 55.4, 58.4),
    ("fireworks", "600 m: 1.7 s late", 61.6, 64.6),
)


def corner_sight_s() -> float:
    """When the walking camera first sees the busker past the corner of the side street's mouth
    (the house at x >= 30, y <= 41.5): the line from the camera to him passes x = 30 at y = 41.5."""
    bx, by, _ = BUSKER
    cy = SIDE_Y
    corner_x, corner_y = SQUARE[1], SIDE_Y - 4.5
    # (xc - corner_x) / (xc - bx) = (cy - corner_y) / (cy - by)
    k = (cy - corner_y) / (cy - by)
    xc = (corner_x - k * bx) / (1 - k)
    return 20.0 + (CORNER_X0 - xc) / WALK_SPEED
